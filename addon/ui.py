"""Desktop course management. All review scheduling stays in native Anki."""
from __future__ import annotations
import hashlib
import html
import json
import time
import statistics
import re
from pathlib import Path
from typing import Callable

from aqt import mw, gui_hooks
from aqt.qt import (QAction, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMessageBox, QPushButton, QSpinBox, QTabWidget, QTextBrowser,
    QTimer, QVBoxLayout, QWidget, Qt, QScrollArea, QGroupBox, QEvent, QObject)
from aqt.operations import CollectionOp
from aqt.utils import showInfo, showWarning, tooltip
from aqt.sound import av_player
from anki.sound import TTSTag, SoundOrVideoTag

from .core import (AUDIO_TYPES, ENTRY_LEVELS, EXERCISE_TYPES, LEVELS,
    admission_decision, level_eligible, load_pack, validate_pack)
from .collection import (get_state, save_state, exercise_notes, prepare_exercise,
    mark_familiarised, activate_exercise, ensure_deck, stage_change, stats)
from .telemetry import LocalData
from .course import COHORTS, load_course, route_candidates, suggested_cohort
from .version import VERSION
from .workload import update_backlog

ROOT = Path(__file__).resolve().parent
_controller = None


def display_type(kind):
    return kind.replace("_", " ").capitalize()


def label(text):
    widget = QLabel(text)
    widget.setWordWrap(True)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


def button(text, callback, layout):
    widget = QPushButton(text)
    widget.clicked.connect(lambda _checked=False: callback())
    layout.addWidget(widget)
    return widget


def payload(note):
    return json.loads(html.unescape(note["Payload"]))


def note_state(note):
    return json.loads(html.unescape(note["State"] or "{}"))


class CourseController:
    def __init__(self):
        profile_hash = hashlib.sha256(mw.pm.profileFolder().encode()).hexdigest()[:20]
        self.local = LocalData(ROOT / "user_files" / profile_hash)
        self.catalog_path = self.local.root / "course-pack.json"
        self.pack = load_course(ROOT, self.catalog_path)
        self.catalog = self.pack["exercises"]
        self.by_id = {e["id"]: e for e in self.catalog}
        self.window = None
        self.prepare_dialog = None
        self.media_ready = False
        self.media_error = ""
        self.paused = False
        self.temporarily_closed = False
        self.last_interaction = time.monotonic()
        self.last_sample = time.monotonic()
        self.attempt_started = None
        self.session_active = 0.0
        self.active_buffer = 0.0
        self.last_tick = time.monotonic()
        self.last_flush = self.last_tick
        self.busy = False
        self.hard_streak = 0
        self.closed = False
        self.clock = QTimer(mw)
        self.clock.setInterval(1000)
        self.clock.timeout.connect(self.tick)
        self.clock.start()
        from .reviewer import register
        self.reviewer = register(self)
        self.install_bundled_audio()


    def install_bundled_audio(self):
        """Install only the package's verified, content-addressed recordings."""
        manifest = ROOT / "data" / "media_manifest.json"
        if not manifest.exists():
            # Compatibility for old developer packs; public Imperial builds require it.
            self.media_ready = not any(e.get("audio_file") for e in self.catalog)
            return
        try:
            from .media import ensure_pack_media
            result = {}
            def install(col):
                result["report"] = ensure_pack_media(col, self.pack, ROOT)
                return col.set_config("comuls_media_version", self.pack["version"], undoable=False)
            def success(_changes):
                self.media_ready = True
                self.media_error = ""
                if self.window:
                    self.window.refresh()
            def failure(error):
                self.media_ready = False
                self.media_error = str(error)
                if self.window:
                    self.window.refresh()
            CollectionOp(parent=mw, op=install).success(success).failure(failure).run_in_background()
        except Exception as error:
            self.media_ready = False
            self.media_error = str(error)

    def pause(self, reason="manual"):
        if self.paused or self.closed:
            return
        self.paused = True
        av_player.stop_and_clear_queue()
        self.flush_time()
        self.on_event({"event": "pause", "reason": reason})
        if QApplication.applicationState() == Qt.ApplicationState.ApplicationActive:
            QTimer.singleShot(0, self.resume_prompt)

    def resume_prompt(self):
        if not self.paused or self.closed or getattr(self, "_resume_dialog_open", False):
            return
        if QApplication.applicationState() != Qt.ApplicationState.ApplicationActive:
            return
        self._resume_dialog_open = True
        dialog = QDialog(self.prepare_dialog or mw)
        dialog.setWindowTitle("COMULS paused")
        box = QVBoxLayout(dialog)
        box.addWidget(label("Your place is saved. Audio is stopped and this pause does not use your daily study time."))
        button("Resume", dialog.accept, box)
        result = dialog.exec()
        self._resume_dialog_open = False
        if result == QDialog.DialogCode.Accepted:
            self.paused = False
            self.last_tick = time.monotonic()
            self.last_interaction = self.last_tick
            self.on_event({"event": "resume"})

    def timings(self):
        default = {"meaning_recall": 8, "french_form_recall": 18, "vocabulary_cloze": 18,
            "grammar_cloze": 18, "grammar_meaning_choice": 12, "sentence_transformation": 40,
            "sound_discrimination": 12, "connected_word_recognition": 12,
            "sentence_reconstruction": 25, "partial_dictation": 25, "sentence_transcription": 40,
            "audio_transcript_choice": 12, "audio_meaning_choice": 12}
        for kind, values in self.state().get("type_timings", {}).items():
            good = [v for v in values if isinstance(v, (int, float)) and 1 <= v <= 300]
            if len(good) >= 20 and kind in default:
                default[kind] = round(statistics.median(good))
        return default

    def evidence(self):
        from .evidence import summarize_exercise
        summaries = {}
        for note in exercise_notes(mw.col).values():
            exercise = payload(note)
            logs = [entry for card in note.cards() for entry in mw.col.get_review_logs(card.id)]
            summaries[exercise["id"]] = summarize_exercise(exercise, note_state(note), logs, time.time())
        return summaries

    def progress_text(self):
        summaries = self.evidence()
        state = self.state()
        rows = []
        for kind in EXERCISE_TYPES:
            ids = [e["id"] for e in self.catalog if e["type"] == kind and e.get("origin_entry_level", state["stage"]) == state["stage"]]
            sampled = [summaries[i] for i in ids if i in summaries]
            stable = sum(bool(item.get("stable")) for item in sampled)
            weak = sum(bool(item.get("repair_needed")) for item in sampled)
            rows.append(display_type(kind) + f": {stable}/{len(sampled)} sampled targets stable; {len(ids)} available; {weak} need repair")
        counts = stats(mw.col)
        return ("Course: Imperial French " + state["stage"] + "\n"
            + f"Introduced cards: {counts['reviewed']} · due: {counts['due']}\n\n"
            + "\n".join(rows) + "\n\n"
            "Stable means two recorded unaided successful reviews on different dates, at least 24 hours after known answer exposure. "
            "Missing assistance coverage is reported conservatively. Native undo removes the undone review's evidence. "
            "These samples do not certify a CEFR level. Timing covers this desktop; synced mobile reviews may have incomplete assistance/time evidence.")

    def try_controls(self):
        dialog = QDialog(self.window or mw)
        dialog.setWindowTitle("Try the four card controls")
        dialog.resize(600, 520)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("These are ungraded examples. Your Anki schedule is not changed."))
        tabs = QTabWidget(); layout.addWidget(tabs)
        reveal = QWidget(); rl = QVBoxLayout(reveal)
        rl.addWidget(label("Meaning recall: Bonjour. Think of the meaning, then reveal."))
        answer = label(""); rl.addWidget(answer)
        button("Show answer", lambda: answer.setText("Hello / good morning. In ordinary study, compare and select your own Anki rating."), rl)
        tabs.addTab(reveal, "Recall")
        typed = QWidget(); tl = QVBoxLayout(typed)
        tl.addWidget(label("Type the French word for hello:"))
        field = QLineEdit(); field.setPlaceholderText("bonjour"); tl.addWidget(field)
        result = label(""); tl.addWidget(result)
        def compare():
            from .core import normalize_answer
            result.setText("Correct. Now you would choose a native Anki rating." if normalize_answer(field.text()) == "bonjour" else "Reference: bonjour. Anki's Again rating means the answer was not retrieved.")
        button("Check", compare, tl); field.returnPressed.connect(compare)
        tabs.addTab(typed, "Type")
        choice = QWidget(); cl = QVBoxLayout(choice)
        cl.addWidget(label("Choose the meaning of merci."))
        feedback = label(""); cl.addWidget(feedback)
        for text, correct in (("Thank you", True), ("Goodbye", False), ("Please", False)):
            button(text, lambda c=correct: feedback.setText("Correct: thank you." if c else "Reference: thank you."), cl)
        tabs.addTab(choice, "Choose")
        tiles = QWidget(); il = QVBoxLayout(tiles)
        il.addWidget(label("Click the tiles to build: Je suis étudiant."))
        row = QHBoxLayout(); il.addLayout(row)
        sequence = []; output = label(""); il.addWidget(output)
        def add(word):
            sequence.append(word); output.setText(" ".join(sequence))
        for word in ("étudiant", "Je", "suis"):
            button(word, lambda word=word: add(word), row)
        button("Reset", lambda: (sequence.clear(), output.setText("")), il)
        tabs.addTab(tiles, "Arrange")
        button("Done", dialog.accept, layout)
        dialog.exec()

    def open_deck_options(self):
        state = self.state()
        deck_id = ensure_deck(mw.col, state)
        from aqt.deckoptions import display_options_for_deck_id
        display_options_for_deck_id(deck_id)

    def on_collection_closing(self, _col=None):
        self.flush_time()
        self.temporarily_closed = True
        self.paused = True
        av_player.stop_and_clear_queue()

    def on_collection_reopened(self, _col=None):
        self.temporarily_closed = False
        self.paused = False
        self.last_tick = time.monotonic()
        self.last_interaction = self.last_tick
        if self.window:
            self.window.refresh()

    def state(self):
        return get_state(mw.col)

    def is_manager(self):
        owner = self.state().get("manager_id")
        return not owner or owner == self.local.manager_id

    def require_manager(self):
        if not self.is_manager():
            showInfo("This collection is managed by another desktop. Reviews still work. "
                     "After syncing both computers, use Settings → Transfer course management here.", parent=self.window)
            return False
        state = self.state()
        if not state.get("manager_id"):
            state["manager_id"] = self.local.manager_id
            save_state(mw.col, state)
        return True

    def show(self):
        if not self.window:
            self.window = CourseWindow(self)
        self.window.refresh()
        if not self.state().get("stage_confirmed", False) or self.state()["stage"] not in COHORTS:
            self.window.tabs.setCurrentIndex(1)
            self.window.stage_box.setCurrentText(suggested_cohort(ROOT))
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def tick(self):
        now = time.monotonic()
        elapsed = min(2.0, max(0.0, now - self.last_tick))
        self.last_tick = now
        if self.closed or self.temporarily_closed or not mw.col:
            return
        active = QApplication.applicationState() == Qt.ApplicationState.ApplicationActive
        if active and self.paused and not getattr(self, "_resume_dialog_open", False):
            QTimer.singleShot(0, self.resume_prompt)
        preparing = self.prepare_dialog is not None and self.prepare_dialog.isActiveWindow()
        reviewing = mw.state == "review" and mw.isActiveWindow() and self.current_is_comuls()
        if active and not self.paused and (preparing or reviewing):
            self.active_buffer += elapsed
            self.session_active += elapsed
            if now - self.last_interaction > 180:
                self.pause("idle")
        elif not active and (self.prepare_dialog is not None or (mw.state == "review" and self.current_is_comuls())) and not self.paused:
            self.pause("focus")
        if now - self.last_flush >= 15 and not self.busy:
            self.flush_time()

    def current_is_comuls(self):
        card = getattr(mw.reviewer, "card", None)
        if not card:
            return False
        try:
            return "COMULS_ID" in card.note()
        except Exception:
            return False

    def add_active_seconds(self, seconds):
        self.active_buffer += max(0, min(float(seconds), 300))

    def flush_time(self):
        if not mw.col or not self.active_buffer:
            return
        state = self.state()
        day = str(mw.col.sched.today)
        days = state.setdefault("days", {})
        record = days.setdefault(day, {})
        record["active_seconds"] = round(record.get("active_seconds", 0) + self.active_buffer, 1)
        state["days"] = dict(sorted(days.items(), key=lambda p: int(p[0]))[-14:])
        save_state(mw.col, state)
        self.active_buffer = 0
        self.last_flush = time.monotonic()

    def today(self):
        state = self.state()
        day = mw.col.sched.today
        return day, state.get("days", {}).get(str(day), {})

    def budget(self):
        state = self.state()
        day, record = self.today()
        timings = self.timings()
        notes = exercise_notes(mw.col)
        units, preview_units, seen_units = set(), set(), set()
        first_days, admitted, due_seconds = {}, 0, 0
        understood = set()
        now = int(time.time())
        for note in notes.values():
            ns, exercise = note_state(note), payload(note)
            unit = ns.get("unit_id", note["COMULS_ID"])
            first_day = ns.get("familiarised_day")
            if first_day is not None:
                first_days[unit] = min(int(first_day), first_days.get(unit, int(first_day)))
                seen_units.add(unit)
            # Understanding declared during preparation is a prerequisite
            # declaration, never a claim of independent retrieval.
            if ns.get("familiarised"):
                understood.add(unit)
            understood.update(ns.get("understood_support", []))
            if ns.get("admitted_day") == str(day):
                admitted += 1
            admission_stage = ns.get("admission_stage", state["stage"])
            if (first_day == str(day) and exercise.get("level") in LEVELS
                    and LEVELS.index(exercise["level"]) > LEVELS.index(admission_stage)):
                preview_units.add(unit)
            for card in note.cards():
                due = ((card.queue == 2 and card.due <= day)
                    or (card.queue == 1 and card.due <= now)
                    or (card.queue == 3 and card.due <= day))
                if due:
                    due_seconds += timings.get(exercise["type"], 25)
        units = {unit for unit, first_day in first_days.items() if first_day == day}
        updated = update_backlog(state, day, due_seconds, state.get("budget_minutes", 15) * 60)
        if updated != state and not self.busy:
            save_state(mw.col, updated)
            state = updated
        seconds = record.get("active_seconds", 0) + self.active_buffer
        extra = record.get("extra_seconds", 0)
        return {"remaining_seconds": max(0, state.get("budget_minutes", 15) * 60 + extra - seconds),
                "new_units": len(units), "admitted_cards": admitted,
                "preview_units": len(preview_units),
                "max_new_units": state.get("max_new_units", 6),
                "max_new_cards": state.get("max_new_cards", 8),
                "max_preview_units": state.get("max_preview_units", 1),
                "due_seconds": due_seconds, "timings": timings,
                "pause_new": bool(state.get("pause_new", False)),
                "override": state.get("backlog_override_day") == day,
                "seen_units": seen_units, "understood": understood, "active_seconds": seconds}

    def on_event(self, event):
        if self.closed or self.temporarily_closed or not mw.col:
            return
        if event.get("event") in ("activity", "question", "attempt", "hint", "replay", "native_grade"):
            self.last_interaction = time.monotonic()
        if event.get("event") == "question":
            self.attempt_started = self.session_active
        if event.get("event") == "native_grade" and self.attempt_started is not None:
            event["active_seconds"] = round(max(0, self.session_active - self.attempt_started), 2)
            self.attempt_started = None
        try:
            self.local.record(event, self.state().get("diagnostics", False) or event.get("event") == "report")
        except OSError:
            tooltip("COMULS could not save local diagnostics. Native reviews are unaffected.")
        if event.get("event") == "report":
            tooltip("Problem recorded locally. Export study data if you choose to share it.")
        if event.get("event") == "question":
            if self.budget()["remaining_seconds"] <= 0:
                QTimer.singleShot(0, self.on_budget_limit)
            elif self.hard_streak >= 3 and event.get("type") in ("sentence_transcription", "sentence_transformation"):
                QTimer.singleShot(0, self.offer_break)
        elif event.get("event") == "native_grade":
            kind = self.by_id.get(event.get("exercise_id"), {}).get("type")
            self.hard_streak = self.hard_streak + 1 if kind in ("sentence_transcription", "sentence_transformation") else 0
            self.flush_time()
            state = self.state()
            if kind and event.get("active_seconds", 0) >= 1:
                samples = state.setdefault("type_timings", {}).setdefault(kind, [])
                samples.append(min(300, event["active_seconds"]))
                state["type_timings"][kind] = samples[-20:]
            counts = stats(mw.col)
            state = update_backlog(state, mw.col.sched.today, self.budget()["due_seconds"],
                state.get("budget_minutes", 15) * 60, completed=True)
            save_state(mw.col, state)

    def offer_break(self):
        if self.closed or mw.state != "review" or not self.current_is_comuls():
            return
        self.hard_streak = 0
        if QMessageBox.question(mw, "A useful stopping point",
            "You have completed several demanding cards. Take a break now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes) == QMessageBox.StandardButton.Yes:
            av_player.stop_and_clear_queue()
            mw.moveToState("deckBrowser")
            self.show()

    def resume_new_today(self):
        if not self.require_manager():
            return
        state = self.state()
        state["backlog_override_day"] = mw.col.sched.today
        save_state(mw.col, state)
        self.on_event({"event": "backlog_override"})
        self.window.refresh()
        showInfo("New learning may resume today if the level, familiarity, daily caps and remaining time allow it.", parent=self.window)

    def on_budget_limit(self):
        if self.closed or not mw.col or mw.state != "review" or not self.current_is_comuls():
            return
        answer = QMessageBox.question(mw, "COMULS daily budget",
            "You have reached your active study budget. Continue for five more minutes?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            state = self.state()
            day = str(mw.col.sched.today)
            record = state.setdefault("days", {}).setdefault(day, {})
            record["extra_seconds"] = record.get("extra_seconds", 0) + 300
            save_state(mw.col, state)
            self.on_event({"event": "budget_override", "seconds": 300})
        else:
            av_player.stop_and_clear_queue()
            mw.moveToState("deckBrowser")
            self.show()

    def content_error(self, text):
        showWarning(str(text), parent=self.window or mw)

    def mutate(self, name: str, operation: Callable, done=None):
        if self.busy or not mw.col:
            return
        self.busy = True
        result = {}
        def op(col):
            undo = col.add_custom_undo_entry(name)
            result["value"] = operation(col)
            return col.merge_undo_entries(undo)
        def success(_changes):
            self.busy = False
            if self.window:
                self.window.refresh()
            if done:
                done(result.get("value"))
        def failure(error):
            self.busy = False
            showWarning(str(error), parent=self.window or mw)
        CollectionOp(parent=self.window or mw, op=op).success(success).failure(failure).run_in_background()

    def study(self):
        if self.busy:
            return
        state = self.state()
        try:
            deck_id = ensure_deck(mw.col, state)
        except Exception as error:
            self.content_error(error)
            return
        self.paused = False
        self.last_interaction = time.monotonic()
        if self.window:
            self.window.hide()
        av_player.stop_and_clear_queue()
        mw.col.decks.select(deck_id)
        mw.moveToState("overview")

    def play(self, text):
        try:
            av_player.play_tags([TTSTag(field_text=text, lang="fr_FR", voices=[], speed=1.0, other_args=[])])
        except Exception as error:
            showWarning("French audio is unavailable: " + str(error), parent=self.window or mw)

    def play_exercise(self, exercise):
        if exercise.get("audio_file"):
            av_player.play_tags([SoundOrVideoTag(filename=exercise["audio_file"])])
        else:
            self.play(exercise.get("audio_text", ""))

    def audio_check(self):
        if not self.media_ready:
            showInfo("The bundled audio is still being installed. " + self.media_error, parent=self.window or mw)
            return
        try:
            from .media import audio_check_filename
            filename = audio_check_filename(ROOT)
        except (ImportError, FileNotFoundError, ValueError):
            filename = None
        if filename:
            av_player.play_tags([SoundOrVideoTag(filename=filename)])
        else:
            self.play("Vous avez entendu une phrase entière. Écoutez comment les mots s'enchaînent.")
        dialog = QMessageBox(self.window or mw)
        dialog.setWindowTitle("French audio check")
        dialog.setText("Did you hear clear French audio?\n\nCheck your output device and volume if you did not. "
                       "The demo includes its French recordings. Listening stays unavailable until you confirm playback works.")
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        state = self.state()
        state["audio_confirmed"] = dialog.exec() == QMessageBox.StandardButton.Yes
        save_state(mw.col, state)
        if self.window:
            self.window.refresh()

    def prepare_next(self, activity=None, repair=False):
        if not self.require_manager() or self.busy:
            return
        state, budget = self.state(), self.budget()
        if not state.get("stage_confirmed", False):
            self.window.tabs.setCurrentIndex(1)
            showInfo("Choose your Imperial B1 or B2 course and click Use this level first.", parent=self.window)
            return
        notes = exercise_notes(mw.col)
        day = mw.col.sched.today
        candidates, blocked = [], {}
        type_counts = {kind: 0 for kind in EXERCISE_TYPES}
        for note in notes.values():
            kind = payload(note).get("type")
            if note_state(note).get("admitted_day") is not None and kind in type_counts:
                type_counts[kind] += 1
        for original in route_candidates(self.catalog, state["stage"], repair):
            exercise = dict(original)
            if activity and exercise["type"] != activity:
                continue
            if repair and LEVELS.index(exercise["level"]) >= LEVELS.index(state["stage"]):
                continue
            note = notes.get(exercise["id"])
            ns = note_state(note) if note else {}
            if note and (any(c.reps > 0 for c in note.cards()) or ns.get("lifecycle") == "admitted"):
                continue
            exercise["unit_already_introduced"] = exercise["unit_id"] in budget["seen_units"]
            decision = admission_decision(exercise, state["stage"], True,
                budget["understood"], set(state.get("enabled", EXERCISE_TYPES)), budget)
            reasons = list(decision["reasons"])
            if exercise["type"] in AUDIO_TYPES and not state.get("audio_confirmed"):
                reasons.append("French audio check required")
            if exercise["type"] in AUDIO_TYPES and exercise.get("audio_file") and not self.media_ready:
                reasons.append("bundled media unavailable")
            # A reverse/companion card is not an independent retrieval on the same day.
            for other in notes.values():
                os = note_state(other)
                if other["COMULS_ID"] != exercise["id"] and os.get("unit_id") == exercise["unit_id"] and os.get("familiarised_day") == str(day):
                    reasons.append("companion available next study day")
                    break
            if reasons:
                for reason in reasons:
                    blocked[reason] = blocked.get(reason, 0) + 1
            else:
                preferred = exercise.get("origin_entry_level") == state["stage"]
                candidates.append((0 if preferred else 1, type_counts[exercise["type"]], exercise["id"], exercise))
        if not candidates:
            details = "\n".join(k.replace("_", " ") + ": " + str(v) for k, v in sorted(blocked.items()))
            showInfo("No new card is available for this selection. Existing reviews remain available.\n\n" + details,
                     parent=self.window)
            return
        exercise = sorted(candidates, key=lambda row: row[:3])[0][3]
        exercise.pop("unit_already_introduced", None)
        self.mutate("Prepare COMULS exercise", lambda col: prepare_exercise(col, exercise, day),
                    lambda _nid: self.familiarise(exercise))

    def familiarise(self, exercise):
        dialog = QDialog(self.window or mw)
        dialog.setWindowTitle("Learn this first — COMULS")
        dialog.resize(660, 540)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label(display_type(exercise["type"]) + " · " + exercise["level"] + " task estimate"))
        layout.addWidget(label("This is supported preparation, not a test. Read the meaning, hear the example if present, "
                               "and check that the surrounding language makes sense."))
        text = QTextBrowser()
        text.setPlainText("\n\n".join(str(exercise.get(k, "")) for k in
            ("prompt", "audio_text", "answer", "target_meaning", "english_support", "carrier_meaning", "explanation") if exercise.get(k)))
        layout.addWidget(text)
        heard = {"value": exercise["type"] not in AUDIO_TYPES}
        if exercise.get("audio_text") or exercise.get("audio_file"):
            def play():
                self.play_exercise(exercise)
                heard["value"] = True
            button("Hear the whole sentence", play, layout)
        understood = QCheckBox("I understand this target and the words/construction used in this example.")
        layout.addWidget(understood)
        layout.addWidget(label("The first review may be helped by this exposure. COMULS does not count it as independent mastery."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add to Anki practice")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Not yet")
        def accept():
            if not understood.isChecked() or not heard["value"]:
                showInfo("Read the explanation and, for listening, play the audio before confirming.", parent=dialog)
                return
            dialog.accept()
        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        self.prepare_dialog = dialog
        result = dialog.exec()
        self.prepare_dialog = None
        av_player.stop_and_clear_queue()
        self.flush_time()
        if result != QDialog.DialogCode.Accepted:
            return
        state, budget = self.state(), self.budget()
        exercise_for_gate = dict(exercise)
        exercise_for_gate["unit_already_introduced"] = exercise["unit_id"] in budget["seen_units"]
        decision = admission_decision(exercise_for_gate, state["stage"], True,
            budget["understood"], set(state.get("enabled", EXERCISE_TYPES)), budget)
        if not decision["allowed"]:
            showInfo("Your preparation is complete, but admission is paused: " + ", ".join(decision["reasons"]), parent=self.window)
            # Preserve actual familiarisation even when the remaining time is exhausted.
            self.mutate("Record COMULS preparation", lambda col: mark_familiarised(col, exercise["id"], col.sched.today))
            return
        def activate(col):
            mark_familiarised(col, exercise["id"], col.sched.today)
            return activate_exercise(col, exercise, col.sched.today)
        self.mutate("Admit COMULS exercise", activate,
                    lambda _nid: tooltip("Added to Anki practice. Use Study due / new cards when ready.", parent=self.window))

    def change_stage(self, stage):
        if not self.require_manager():
            return
        def apply(col):
            result = stage_change(col, stage, self.catalog)
            state = get_state(col)
            state["stage_confirmed"] = True
            state["cohort"] = stage
            save_state(col, state)
            return result
        self.mutate("Change COMULS entry level", apply,
            lambda _result: self.window.tabs.setCurrentIndex(0))

    def preview(self, exercise):
        dialog = QDialog(self.window or mw)
        dialog.setWindowTitle("COMULS library — ungraded")
        dialog.resize(640, 500)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Reference preview. This does not add a card, mark knowledge or change your level."))
        text = QTextBrowser()
        text.setPlainText("\n\n".join([display_type(exercise["type"]) + " · " + exercise["level"],
            exercise["prompt"], exercise.get("audio_text", ""), exercise["answer"],
            exercise.get("explanation", ""), exercise.get("carrier_meaning", ""),
            "Level assignment: provisional task estimate."]))
        layout.addWidget(text)
        if exercise.get("audio_text") or exercise.get("audio_file"):
            button("Play whole sentence", lambda: self.play_exercise(exercise), layout)
        button("Close", dialog.accept, layout)
        from .collection import record_reference_exposure
        record_reference_exposure(mw.col, exercise["id"], time.time())
        self.on_event({"event": "reference_preview", "exercise_id": exercise["id"]})
        dialog.exec()
        av_player.stop_and_clear_queue()

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self.window, "Export COMULS study data", "comuls-study-data.json", "JSON (*.json)")
        if not path:
            return
        self.flush_time()
        records = []
        for note in exercise_notes(mw.col).values():
            for card in note.cards():
                logs = []
                for review in mw.col.get_review_logs(card.id):
                    logs.append({k: getattr(review, k, None) for k in
                        ("time", "review_kind", "button_chosen", "interval", "taken_secs")})
                records.append({"exercise_id": note["COMULS_ID"], "reviews": logs, "state": note_state(note)})
        state = self.state()
        export = {"schema_version": 1, "pack_id": self.pack["pack_id"], "pack_version": self.pack["version"],
            "stage": state["stage"], "cohort": state.get("cohort", state["stage"]),
            "addon_version": VERSION, "evidence": self.evidence(), "days": state.get("days", {}), "cards": records,
            "events": self.local.events(), "measurement_notes":
            ["Native review history is authoritative and reflects undo.",
             "Optional detailed events and active time cover this desktop only.",
             "Ratings are learner reports, not independently measured fluency.",
             "No name, email, profile path, raw typed answer or device ID is included."]}
        Path(path).write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
        showInfo("Study data exported. Nothing was uploaded.", parent=self.window)

    def content_manager(self):
        dialog = QDialog(self.window or mw)
        dialog.setWindowTitle("COMULS content manager")
        dialog.resize(780, 610)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Installed course: " + self.pack["pack_id"] + " · " + self.pack["version"]
            + "\nMedia: " + ("verified and available" if self.media_ready else "unavailable — " + self.media_error)))
        listing = QListWidget(); layout.addWidget(listing)
        from aqt.qt import QListWidgetItem
        def refresh():
            listing.clear()
            for note in exercise_notes(mw.col).values():
                exercise, state = payload(note), note_state(note)
                status = state.get("lifecycle", "prepared")
                if state.get("managed_pause"):
                    status += " · paused"
                item = QListWidgetItem(exercise["level"] + " · " + display_type(exercise["type"])
                    + " · " + exercise["answer"] + " · " + status)
                item.setData(Qt.ItemDataRole.UserRole, exercise["id"])
                listing.addItem(item)
        def selected():
            item = listing.currentItem()
            return item.data(Qt.ItemDataRole.UserRole) if item else None
        def change(action):
            identity = selected()
            if not identity:
                return
            from .collection import set_managed_pause
            self.mutate("Change COMULS managed pause",
                lambda col: set_managed_pause(col, [identity], action == "pause", "user"),
                lambda _result: refresh())
        row = QHBoxLayout(); layout.addLayout(row)
        button("Pause selected", lambda: change("pause"), row)
        button("Restore selected", lambda: change("restore"), row)
        button("Open reference", lambda: self.preview(self.by_id[selected()]) if selected() in self.by_id else None, row)
        layout.addWidget(label("Restore affects only COMULS-owned pauses. Personal Anki suspensions, review history and due dates are preserved."))
        row = QHBoxLayout(); layout.addLayout(row)
        button("Install course pack…", self.install_pack, row)
        button("Verify / restore bundled audio", self.install_bundled_audio, row)
        button("Close", dialog.accept, row)
        refresh()
        dialog.exec()

    def install_pack(self):
        if not self.require_manager():
            return
        path, _ = QFileDialog.getOpenFileName(self.window, "Install declarative course pack", "", "JSON (*.json)")
        if not path:
            return
        try:
            file = Path(path)
            if file.stat().st_size > 8_000_000:
                raise ValueError("Course packs are limited to 8 MB in this tester.")
            pack = load_pack(file)
            merged = {e["id"]: e for e in self.catalog}
            for exercise in pack["exercises"]:
                audio = exercise.get("audio_file", "")
                if audio and (Path(audio).name != audio or ":" in audio or "[" in audio):
                    raise ValueError("Audio must name a collection media file, not a path or URL.")
                if audio and not (Path(mw.col.media.dir()) / audio).is_file():
                    raise ValueError("Missing collection audio: " + audio)
                merged[exercise["id"]] = exercise
            combined = dict(pack, exercises=list(merged.values()))
            errors = validate_pack(combined)
            if errors:
                raise ValueError("\n".join(errors))
            notes = exercise_notes(mw.col)
            def install(col):
                for exercise in pack["exercises"]:
                    if exercise["id"] in notes:
                        prepare_exercise(col, exercise, col.sched.today)
                return True
            def save(_result):
                self.catalog_path.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
                self.pack, self.catalog = combined, combined["exercises"]
                self.by_id = {e["id"]: e for e in self.catalog}
                self.window.refresh()
                showInfo("Pack installed. Existing identities and review history were preserved.", parent=self.window)
            self.mutate("Update COMULS content", install, save)
        except Exception as error:
            self.content_error(error)

    def close(self):
        if self.closed:
            return
        self.flush_time()
        self.closed = True
        self.clock.stop()
        av_player.stop_and_clear_queue()
        if hasattr(self.reviewer, "close"):
            self.reviewer.close()
        if self.window:
            self.window.close()


class CourseWindow(QDialog):
    def __init__(self, controller):
        super().__init__(mw)
        self.c = controller
        self.setWindowTitle("COMULS — Imperial French demo")
        self.resize(830, 670)
        self.setMinimumSize(610, 470)
        layout = QVBoxLayout(self)
        title = label("COMULS · Imperial French")
        title.setStyleSheet("font-size: 23px; padding: 8px 0;")
        layout.addWidget(title)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.home = QWidget(); self.home_layout = QVBoxLayout(self.home)
        self.summary = label(""); self.home_layout.addWidget(self.summary)
        button("Study due / new cards in Anki", self.c.study, self.home_layout)
        self.activity = QComboBox(); self.activity.addItem("All exercise types", None)
        for kind in EXERCISE_TYPES:
            self.activity.addItem(display_type(kind), kind)
        self.home_layout.addWidget(self.activity)
        button("Prepare one new exercise", lambda: self.c.prepare_next(self.activity.currentData()), self.home_layout)
        button("Prepare lower-level repair", lambda: self.c.prepare_next(self.activity.currentData(), True), self.home_layout)
        button("Check French audio", self.c.audio_check, self.home_layout)
        button("Try the card controls", self.c.try_controls, self.home_layout)
        button("Resume new learning today despite backlog", self.c.resume_new_today, self.home_layout)
        self.home_layout.addWidget(label("Prepare only what fits today. Anki schedules the cards you have introduced. "
            "Show the answer and choose Again / Hard / Good / Easy yourself; COMULS never rates for you."))
        self.home_layout.addStretch()
        self.tabs.addTab(self.home, "Home")
        self.levels = QWidget(); levels_layout = QVBoxLayout(self.levels)
        levels_layout.addWidget(label("Choose your current entry level. Existing reviews remain available. "
            "Cloze and synthesis tasks stay below it; supported listening can use higher bands. "
            "These labels guide this tester and do not certify CEFR proficiency."))
        self.stage_box = QComboBox(); self.stage_box.addItems(list(COHORTS)); levels_layout.addWidget(self.stage_box)
        button("Use this level", lambda: self.c.change_stage(self.stage_box.currentText()), levels_layout)
        self.coverage = QTextBrowser(); levels_layout.addWidget(self.coverage)
        self.tabs.addTab(self.levels, "Levels")
        library = QWidget(); ll = QVBoxLayout(library)
        self.search = QLineEdit(); self.search.setPlaceholderText("Find an exercise, word or type"); ll.addWidget(self.search)
        self.library = QListWidget(); ll.addWidget(self.library)
        self.search.textChanged.connect(self.filter_library)
        self.library.itemDoubleClicked.connect(lambda item: self.c.preview(item.data(Qt.ItemDataRole.UserRole)))
        button("Open selected reference", self.open_selected, ll)
        self.tabs.addTab(library, "Library")
        progress = QWidget(); pl = QVBoxLayout(progress)
        self.progress = QTextBrowser(); pl.addWidget(self.progress)
        button("Export study data…", self.c.export, pl)
        button("Record today's effort / fatigue", self.fatigue, pl)
        self.tabs.addTab(progress, "Progress")
        settings = QScrollArea(); settings.setWidgetResizable(True)
        settings_body = QWidget(); sl = QVBoxLayout(settings_body); settings.setWidget(settings_body)
        form = QFormLayout(); sl.addLayout(form)
        self.minutes = QSpinBox(); self.minutes.setRange(5, 90); form.addRow("Daily active minutes", self.minutes)
        self.units = QSpinBox(); self.units.setRange(0, 20); form.addRow("New targets per day", self.units)
        self.cards = QSpinBox(); self.cards.setRange(0, 30); form.addRow("New cards per day", self.cards)
        self.previews = QSpinBox(); self.previews.setRange(0, 1); form.addRow("Above-stage new targets per day", self.previews)
        self.font_size = QSpinBox(); self.font_size.setRange(85, 160); self.font_size.setSuffix("%"); form.addRow("Card text size", self.font_size)
        self.accent_row = QCheckBox("Show French accent keys"); sl.addWidget(self.accent_row)
        self.autoplay = QCheckBox("Play the primary recording automatically on listening questions"); sl.addWidget(self.autoplay)
        self.startup = QCheckBox("Open COMULS when this profile opens"); sl.addWidget(self.startup)
        self.diagnostics = QCheckBox("Keep optional local study diagnostics (no automatic upload)"); sl.addWidget(self.diagnostics)
        self.checks = {}
        for kind in EXERCISE_TYPES:
            check = QCheckBox(display_type(kind)); self.checks[kind] = check; sl.addWidget(check)
        sl.addWidget(label("These switches control new admission. Existing cards keep their Anki schedule. "
                           "Use Content manager to pause and restore existing exercises."))
        button("Save settings", self.save_settings, sl)
        row = QHBoxLayout(); sl.addLayout(row)
        button("Content manager…", self.c.content_manager, row)
        button("Transfer course management here", self.transfer, row)
        button("Delete local diagnostics", self.delete_logs, row)
        button("Native Anki deck options", self.c.open_deck_options, sl)
        self.tabs.addTab(settings, "Settings")
        about = QTextBrowser(); about.setPlainText(
            "COMULS Imperial French demo · " + VERSION + "\n\n"
            "Desktop compatibility target: Anki 26.09.3. Install the B1 or B2 package for your course. "
            "Both routes use thirteen short flashcard formats and native Anki scheduling.\n\n"
            "The included course is an original pilot pack. Vocabulary source levels are unchanged; exercise-level "
            "estimates are provisional. Lower-level synthesis and supported higher-level listening are intentional.\n\n"
            "French recordings are bundled for offline playback. The audio manifest records the voice, licence and "
            "exact file hashes. Answer-side listening uses recorded whole utterances and available aligned chunks.\n\n"
            "Anki sync carries cards, media and native review history. Manage admissions from one desktop. "
            "Mobile review has reduced management, assistance and timing coverage.\n\n"
            "No study data is uploaded automatically. Reports stay on this computer until you export them. "
            "Course activity and stable sampled targets do not certify a CEFR level or establish improved fluency. "
            "An effectiveness study needs independent delayed assessments.")
        self.tabs.addTab(about, "About")
        button("Refresh", self.refresh, layout)

    def refresh(self):
        if not mw.col or self.c.closed:
            return
        try:
            state = self.c.state(); counts = stats(mw.col); budget = self.c.budget()
        except Exception as error:
            self.summary.setText("COMULS needs attention: " + str(error))
            return
        self.stage_box.setCurrentText(state["stage"])
        self.minutes.setValue(state.get("budget_minutes", 15))
        self.units.setValue(state.get("max_new_units", 6))
        self.cards.setValue(state.get("max_new_cards", 8))
        self.previews.setValue(state.get("max_preview_units", 1))
        self.font_size.setValue(state.get("font_percent", 100))
        self.accent_row.setChecked(state.get("accent_row", True))
        self.autoplay.setChecked(state.get("audio_autoplay", False))
        self.startup.setChecked(state.get("open_on_startup", False))
        self.diagnostics.setChecked(state.get("diagnostics", False))
        for kind, check in self.checks.items():
            check.setChecked(kind in state.get("enabled", EXERCISE_TYPES))
        self.summary.setText(f"Entry level {state['stage']} · {counts.get('due', 0)} due · "
            f"{counts.get('new', 0)} admitted new cards\n"
            f"{round(budget['remaining_seconds'] / 60, 1)} active minutes left today · "
            f"{budget['new_units']}/{budget['max_new_units']} new targets · {budget['admitted_cards']}/{budget['max_new_cards']} new cards\n"
            f"{budget['preview_units']}/{budget['max_preview_units']} above-stage new targets today\n"
            + ("French audio confirmed." if state.get("audio_confirmed") else "Run the French audio check before listening.")
            + ("" if self.c.is_manager() else "\nCourse management belongs to another desktop; native review is available."))
        lines = []
        for stage in COHORTS:
            available = [e for e in route_candidates(self.c.catalog, stage) if level_eligible(e, stage)]
            bands = sorted({e["level"] for e in available}, key=LEVELS.index)
            lines.append(stage + ": " + str(len(available)) + " catalog exercises; task bands " + ", ".join(bands))
        lines.append("\nHalf-level labels are COMULS subdivisions. Library previews are ungraded; admission requires "
                     "per-exercise familiarisation, available audio, enabled formats and remaining budget.")
        self.coverage.setPlainText("\n\n".join(lines))
        self.filter_library()
        self.progress.setPlainText(self.c.progress_text())

    def filter_library(self, _text=None):
        self.library.clear()
        query = self.search.text().casefold().strip()
        for exercise in self.c.catalog:
            text = exercise["level"] + " · " + display_type(exercise["type"]) + " · " + exercise["prompt"].split("\n")[0]
            if query and query not in (text + " " + exercise["answer"]).casefold():
                continue
            from aqt.qt import QListWidgetItem
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, exercise)
            self.library.addItem(item)

    def open_selected(self):
        item = self.library.currentItem()
        if item:
            self.c.preview(item.data(Qt.ItemDataRole.UserRole))

    def save_settings(self):
        if not self.c.require_manager():
            return
        state = self.c.state()
        state["budget_minutes"] = self.minutes.value()
        state["max_new_units"] = self.units.value()
        state["max_new_cards"] = self.cards.value()
        state["max_preview_units"] = self.previews.value()
        state["font_percent"] = self.font_size.value()
        state["accent_row"] = self.accent_row.isChecked()
        state["audio_autoplay"] = self.autoplay.isChecked()
        state["open_on_startup"] = self.startup.isChecked()
        state["diagnostics"] = self.diagnostics.isChecked()
        state["enabled"] = [kind for kind, check in self.checks.items() if check.isChecked()]
        save_state(mw.col, state)
        self.refresh()
        tooltip("COMULS settings saved.", parent=self)

    def transfer(self):
        answer = QMessageBox.question(self, "Transfer course management",
            "Sync this collection and the previous managing desktop first. Has that sync completed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            state = self.c.state(); state["manager_id"] = self.c.local.manager_id
            save_state(mw.col, state); self.refresh()

    def delete_logs(self):
        if QMessageBox.question(self, "Delete local diagnostics",
            "Delete only COMULS's optional local event log? Anki review history will remain.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.c.local.clear()
            tooltip("Local diagnostic log deleted.", parent=self)

    def fatigue(self):
        dialog = QDialog(self); dialog.setWindowTitle("Today's effort"); layout = QVBoxLayout(dialog)
        layout.addWidget(label("How tiring did today's COMULS practice feel?"))
        box = QComboBox(); box.addItems(["1 — very light", "2 — light", "3 — moderate", "4 — tiring", "5 — very tiring"])
        box.setCurrentIndex(2); layout.addWidget(box)
        def save():
            state = self.c.state(); day = str(mw.col.sched.today)
            state.setdefault("days", {}).setdefault(day, {})["fatigue"] = box.currentIndex() + 1
            save_state(mw.col, state)
            self.c.on_event({"event": "fatigue", "rating": box.currentIndex() + 1})
            dialog.accept()
        button("Save", save, layout); dialog.exec()


def open_comuls():
    global _controller
    if not mw.col:
        showInfo("Open an Anki profile first.")
        return
    try:
        if _controller is None or _controller.closed:
            _controller = CourseController()
        _controller.show()
    except Exception as error:
        showWarning("COMULS could not open: " + str(error))


def on_profile_open():
    global _controller
    if _controller is not None:
        _controller.close()
    try:
        _controller = CourseController()
        config = mw.addonManager.getConfig(__name__) or {}
        if _controller.state().get("open_on_startup", config.get("open_on_startup", False)):
            _controller.show()
    except Exception as error:
        showWarning("COMULS could not start: " + str(error))


def on_profile_close():
    global _controller
    if _controller:
        _controller.close()
    _controller = None


def setup():
    if getattr(mw, "_comuls_menu_installed", False):
        return
    mw._comuls_menu_installed = True
    action = QAction("COMULS", mw)
    action.triggered.connect(open_comuls)
    mw.form.menuTools.addAction(action)
    gui_hooks.profile_did_open.append(on_profile_open)
    gui_hooks.profile_will_close.append(on_profile_close)
    gui_hooks.deck_browser_will_render_content.append(deck_browser_content)
    gui_hooks.webview_did_receive_js_message.append(navigation_message)
    gui_hooks.collection_will_temporarily_close.append(collection_closing)
    gui_hooks.collection_did_temporarily_close.append(collection_reopened)


def deck_browser_content(_browser, content):
    content.stats += '<div style="margin:18px"><button onclick="pycmd(\'comuls:open\')">COMULS · French course</button></div>'


def navigation_message(handled, message, context):
    from aqt.deckbrowser import DeckBrowser
    if not handled[0] and isinstance(context, DeckBrowser) and message == "comuls:open":
        open_comuls()
        return (True, None)
    return handled


def collection_closing(col):
    if _controller is not None:
        _controller.on_collection_closing(col)


def collection_reopened(col):
    if _controller is not None and not _controller.closed:
        _controller.on_collection_reopened(col)

"""Desktop course management. All review scheduling stays in native Anki."""
from __future__ import annotations
import hashlib
import html
import json
import time
from pathlib import Path
from typing import Callable

from aqt import mw, gui_hooks
from aqt.qt import (QAction, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMessageBox, QPushButton, QSpinBox, QTabWidget, QTextBrowser,
    QTimer, QVBoxLayout, QWidget, Qt)
from aqt.operations import CollectionOp
from aqt.utils import showInfo, showWarning, tooltip
from aqt.sound import av_player
from anki.sound import TTSTag, SoundOrVideoTag

from .core import (AUDIO_TYPES, ENTRY_LEVELS, EXERCISE_TYPES, LEVELS,
    admission_decision, level_eligible, load_pack, validate_pack)
from .collection import (get_state, save_state, exercise_notes, prepare_exercise,
    mark_familiarised, activate_exercise, ensure_deck, stage_change, stats)
from .telemetry import LocalData

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
        self.pack = load_pack(self.catalog_path if self.catalog_path.exists() else ROOT / "data" / "tester.json")
        self.catalog = self.pack["exercises"]
        self.by_id = {e["id"]: e for e in self.catalog}
        self.window = None
        self.prepare_dialog = None
        self.active_buffer = 0.0
        self.last_tick = time.monotonic()
        self.last_flush = self.last_tick
        self.busy = False
        self.closed = False
        self.clock = QTimer(mw)
        self.clock.setInterval(1000)
        self.clock.timeout.connect(self.tick)
        self.clock.start()
        from .reviewer import register
        self.reviewer = register(self)

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
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def tick(self):
        now = time.monotonic()
        elapsed = min(2.0, max(0.0, now - self.last_tick))
        self.last_tick = now
        if self.closed or not mw.col:
            return
        active = QApplication.applicationState() == Qt.ApplicationState.ApplicationActive
        preparing = self.prepare_dialog is not None and self.prepare_dialog.isActiveWindow()
        reviewing = mw.state == "review" and mw.isActiveWindow() and self.current_is_comuls()
        if active and (preparing or reviewing):
            self.active_buffer += elapsed
        elif not active:
            av_player.stop_and_clear_queue()
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
        counts = stats(mw.col)
        day, record = self.today()
        units, admitted, seen_units = set(), 0, set()
        for note in exercise_notes(mw.col).values():
            ns = note_state(note)
            if ns.get("familiarised_day") == str(day):
                units.add(ns.get("unit_id", note["COMULS_ID"]))
            if ns.get("admitted_day") == str(day):
                admitted += 1
            if ns.get("familiarised_day") is not None:
                seen_units.add(ns.get("unit_id", note["COMULS_ID"]))
        seconds = record.get("active_seconds", 0) + self.active_buffer
        extra = record.get("extra_seconds", 0)
        return {"remaining_seconds": max(0, state.get("budget_minutes", 15) * 60 + extra - seconds),
                "new_units": len(units), "admitted_cards": admitted,
                "due_seconds": counts.get("due", 0) * 25,
                "pause_new": bool(state.get("pause_new", False)),
                "override": state.get("backlog_override_day") == day,
                "seen_units": seen_units, "active_seconds": seconds}

    def on_event(self, event):
        if self.closed or not mw.col:
            return
        try:
            self.local.record(event, self.state().get("diagnostics", False))
        except OSError:
            tooltip("COMULS could not save local diagnostics. Native reviews are unaffected.")
        if event.get("event") == "question":
            if self.budget()["remaining_seconds"] <= 0:
                QTimer.singleShot(0, self.on_budget_limit)
        elif event.get("event") == "native_grade":
            self.flush_time()

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
        self.play("Vous avez entendu une phrase entière. Écoutez comment les mots s'enchaînent.")
        dialog = QMessageBox(self.window or mw)
        dialog.setWindowTitle("French audio check")
        dialog.setText("Did you hear clear French audio?\n\nIf not, install a French system voice and restart Anki. "
                       "Linux requires an Anki TTS add-on. Listening stays unavailable until you confirm it works.")
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
        notes = exercise_notes(mw.col)
        day = mw.col.sched.today
        candidates, blocked = [], {}
        type_counts = {kind: 0 for kind in EXERCISE_TYPES}
        for note in notes.values():
            kind = payload(note).get("type")
            if note_state(note).get("admitted_day") is not None and kind in type_counts:
                type_counts[kind] += 1
        for original in self.catalog:
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
                budget["seen_units"], set(state.get("enabled", EXERCISE_TYPES)), budget)
            reasons = list(decision["reasons"])
            if exercise["type"] in AUDIO_TYPES and not state.get("audio_confirmed"):
                reasons.append("French audio check required")
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
            ("prompt", "audio_text", "answer", "target_meaning", "carrier_meaning", "explanation") if exercise.get(k)))
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
            budget["seen_units"], set(state.get("enabled", EXERCISE_TYPES)), budget)
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
        if not self.require_manager() or stage == self.state()["stage"]:
            return
        self.mutate("Change COMULS entry level", lambda col: stage_change(col, stage, self.catalog))

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
            "stage": state["stage"], "days": state.get("days", {}), "cards": records,
            "events": self.local.events(), "measurement_notes":
            ["Native review history is authoritative and reflects undo.",
             "Optional detailed events and active time cover this desktop only.",
             "Ratings are learner reports, not independently measured fluency.",
             "No name, email, profile path, raw typed answer or device ID is included."]}
        Path(path).write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
        showInfo("Study data exported. Nothing was uploaded.", parent=self.window)

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
        self.setWindowTitle("COMULS — French practice")
        self.resize(830, 670)
        self.setMinimumSize(610, 470)
        layout = QVBoxLayout(self)
        title = label("COMULS · concurrent French practice")
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
        self.home_layout.addWidget(label("Prepare only what fits today. Anki schedules the cards you have introduced. "
            "Show the answer and choose Again / Hard / Good / Easy yourself; COMULS never rates for you."))
        self.home_layout.addStretch()
        self.tabs.addTab(self.home, "Home")
        self.levels = QWidget(); levels_layout = QVBoxLayout(self.levels)
        levels_layout.addWidget(label("Choose your current entry level. Existing reviews remain available. "
            "Cloze and synthesis tasks stay below it; supported listening can use higher bands. "
            "These labels guide this tester and do not certify CEFR proficiency."))
        self.stage_box = QComboBox(); self.stage_box.addItems(list(ENTRY_LEVELS)); levels_layout.addWidget(self.stage_box)
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
        settings = QWidget(); sl = QVBoxLayout(settings)
        form = QFormLayout(); sl.addLayout(form)
        self.minutes = QSpinBox(); self.minutes.setRange(5, 90); form.addRow("Daily active minutes", self.minutes)
        self.diagnostics = QCheckBox("Keep optional local study diagnostics (no automatic upload)"); sl.addWidget(self.diagnostics)
        self.checks = {}
        for kind in EXERCISE_TYPES:
            check = QCheckBox(display_type(kind)); self.checks[kind] = check; sl.addWidget(check)
        sl.addWidget(label("These switches control new admission. Existing cards keep their Anki schedule. "
                           "Use Anki's Browse → Suspend for a deliberate pause of existing cards."))
        button("Save settings", self.save_settings, sl)
        row = QHBoxLayout(); sl.addLayout(row)
        button("Install course pack…", self.c.install_pack, row)
        button("Transfer course management here", self.transfer, row)
        button("Delete local diagnostics", self.delete_logs, row)
        self.tabs.addTab(settings, "Settings")
        about = QTextBrowser(); about.setPlainText(
            "COMULS tester\n\nInstall target: Anki Desktop 26.09.3 or later.\n\n"
            "This is a small original content pack covering all thirteen formats. It is not the full vocabulary course. "
            "Task-level estimates are provisional and existing vocabulary expression ratings remain unchanged.\n\n"
            "French audio uses Anki's native text-to-speech. Check the installed voice before listening practice. "
            "The tester does not include a human-reviewed recording pack or validated word-boundary timestamps.\n\n"
            "Cards and scheduling sync through normal Anki sync. Manage new admissions from one designated desktop. "
            "Mobile review is a compatibility candidate; mobile admission, detailed timing and add-on controls are not available.\n\n"
            "This tester can support usability feedback. It is not evidence that COMULS improves fluency or learning speed. "
            "Use independent delayed assessments for an effectiveness study.\n\n"
            "Report a problematic card through its Report control; reports remain local. Export study data if you choose to share it.")
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
        self.diagnostics.setChecked(state.get("diagnostics", False))
        for kind, check in self.checks.items():
            check.setChecked(kind in state.get("enabled", EXERCISE_TYPES))
        self.summary.setText(f"Entry level {state['stage']} · {counts.get('due', 0)} due · "
            f"{counts.get('new', 0)} admitted new cards\n"
            f"{round(budget['remaining_seconds'] / 60, 1)} active minutes left today · "
            f"{budget['new_units']}/6 new units · {budget['admitted_cards']}/8 new cards\n"
            + ("French audio confirmed." if state.get("audio_confirmed") else "Run the French audio check before listening.")
            + ("" if self.c.is_manager() else "\nCourse management belongs to another desktop; native review is available."))
        lines = []
        for stage in ENTRY_LEVELS:
            available = [e for e in self.c.catalog if level_eligible(e, stage)]
            bands = sorted({e["level"] for e in available}, key=LEVELS.index)
            lines.append(stage + ": " + str(len(available)) + " catalog exercises; task bands " + ", ".join(bands))
        lines.append("\nHalf-level labels are COMULS subdivisions. Library previews are ungraded; admission requires "
                     "per-exercise familiarisation, available audio, enabled formats and remaining budget.")
        self.coverage.setPlainText("\n\n".join(lines))
        self.filter_library()
        self.progress.setPlainText(
            f"Introduced native cards: {counts.get('reviewed', 0)}\n"
            f"Managed cards: {counts.get('total', 0)}\n"
            f"Active study on this desktop today: {round(budget['active_seconds']/60, 1)} minutes\n\n"
            "These are activity measures, not a CEFR score. Anki's review history is authoritative and respects native undo. "
            "Assisted answers and immediate preparation do not demonstrate independent mastery.\n\n"
            "Timing excludes unfocused windows. Reviews on other devices and periods with the add-on unavailable "
            "make time coverage incomplete. Optional diagnostics are stored locally and exported only on request.")

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
        if config.get("open_on_startup", False):
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

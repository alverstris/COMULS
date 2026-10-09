"""Injected test add-on driving an unmodified aqt.run application.

All student actions use actual Qt controls or DOM events in native webviews.
The only fixtures are disposable preferences and an editorial JSON import.
"""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import time
import traceback
import wave

import aqt
from aqt import gui_hooks
from aqt.qt import QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QLineEdit, QMessageBox, QPushButton, QScrollArea, QTabWidget, QTimer, Qt
from PyQt6.QtTest import QTest
from PyQt6 import sip
from aqt.sound import av_player


def visible(widget):
    # Qt's static file/message helpers delete their C++ dialog after choice.
    return not sip.isdeleted(widget) and widget.isVisible()


class Wait:
    def __init__(self, predicate, description, timeout=45):
        self.predicate = predicate
        self.description = description
        self.deadline = time.monotonic() + timeout


class Driver:
    def __init__(self, config):
        self.config = config
        self.output = Path(config["artifact_dir"])
        self.report = {"run_id": config["run_id"], "phase": config["phase"],
                       "stage": config.get("stage"), "source_commit": config["source_commit"],
                       "package_sha256": config["package_sha256"],
                       "source_tree_sha256": config["source_tree_sha256"], "passed": False, "reviews": [],
                       "checks": [], "screenshots": [], "audio": [],
                       "fixture_scope": ["Disposable native Anki preferences/profile", "Editorial import JSON"],
                       "student_scenario": "Displayed baseline carrier uses explicitly declared already understood through UI; no knowledge seeded"}
        self.wait = None
        self.running = False
        self.finished = False
        self.started = time.monotonic()
        self.generator = self.steps()
        self.timer = QTimer(aqt.mw)
        self.timer.setInterval(60)
        self.timer.timeout.connect(self.tick)
        gui_hooks.av_player_did_begin_playing.append(self.audio_begin)
        gui_hooks.av_player_did_end_playing.append(self.audio_end)
        self.ends = 0
        self.timer.start()

    def audio_begin(self, player, tag):
        filename = getattr(tag, "filename", None)
        expected = None
        if filename and aqt.mw.col:
            with wave.open(str(Path(aqt.mw.col.media.dir()) / filename), "rb") as wav:
                expected = wav.getnframes() / wav.getframerate()
        self.report["audio"].append({"player": type(player).__name__, "tag": type(tag).__name__,
                                    "filename": filename, "expected_seconds": expected,
                                    "elapsed": round(time.monotonic()-self.started, 3)})

    def audio_end(self, player):
        self.ends += 1
        for record in reversed(self.report["audio"]):
            if record["player"] == type(player).__name__ and "playback_seconds" not in record:
                record["playback_seconds"] = round(time.monotonic()-self.started-record["elapsed"], 3)
                break

    def recording_completed_since(self, index):
        records = self.report["audio"][index:]
        if not records or av_player.current_player is not None or any("playback_seconds" not in r for r in records):
            return False
        for record in records:
            assert record["expected_seconds"] is not None, "Expected real bundled WAV playback"
            assert record["playback_seconds"] >= record["expected_seconds"] * .7, (
                "Native player ended too quickly to play the recording; process failure is not successful audio: " + str(record))
        return True

    def tick(self):
        if self.running or self.finished:
            return
        self.running = True
        try:
            if time.monotonic()-self.started > 560:
                raise TimeoutError("Whole real-Anki scenario exceeded 560 seconds")
            if self.wait:
                if not self.wait.predicate():
                    if time.monotonic() > self.wait.deadline:
                        raise TimeoutError(self.wait.description + "; visible dialogs: " + repr(self.dialogs()))
                    return
                self.wait = None
            self.wait = next(self.generator)
            if not isinstance(self.wait, Wait):
                raise AssertionError("Driver yielded an invalid wait")
        except StopIteration:
            self.report["passed"] = True
            self.finish()
        except Exception:
            self.report["error"] = traceback.format_exc()
            self.finish()
        finally:
            self.running = False

    def finish(self):
        self.finished = True
        self.timer.stop()
        self.screenshot("final", aqt.mw)
        self.report["elapsed_seconds"] = round(time.monotonic()-self.started, 2)
        self.report["visible_dialogs"] = self.dialogs()
        Path(self.config["report_path"]).write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"run": self.config["run_id"], "passed": self.report["passed"],
                          "error": self.report.get("error")}), flush=True)
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QDialog) and widget.isVisible():
                widget.reject()
        QTimer.singleShot(0, aqt.mw.unloadProfileAndExit)

    def dialogs(self):
        return [{"type": type(w).__name__, "title": w.windowTitle(),
                 "text": w.text() if isinstance(w, QMessageBox) else ""}
                for w in QApplication.topLevelWidgets() if isinstance(w, QDialog) and w.isVisible()]

    def modal(self, title=None, text=None):
        for widget in QApplication.topLevelWidgets():
            if not isinstance(widget, QDialog) or not widget.isVisible():
                continue
            if title and title not in widget.windowTitle():
                continue
            if text and (not isinstance(widget, QMessageBox) or text not in widget.text()):
                continue
            return widget
        return None

    def schedule(self, callback):
        # Modal widget callbacks run their real nested Qt event loop. The driver
        # keeps ticking so it can interact with the dialog while that loop runs.
        def invoke():
            try:
                callback()
            except Exception:
                if not self.finished:
                    self.report["error"] = traceback.format_exc()
                    self.finish()
        QTimer.singleShot(0, invoke)

    def click(self, parent, text, contains=False):
        buttons = [b for b in parent.findChildren(QPushButton)
                   if (text.casefold() in b.text().casefold() if contains else b.text() == text) and b.isVisible()]
        if len(buttons) != 1 or not buttons[0].isEnabled():
            raise AssertionError(f"Expected one enabled visible button {text!r}; found {[b.text() for b in buttons]}")
        for area in parent.findChildren(QScrollArea):
            if area.isAncestorOf(buttons[0]):
                area.ensureWidgetVisible(buttons[0])
        self.schedule(lambda: QTest.mouseClick(buttons[0], Qt.MouseButton.LeftButton))

    def pause(self, seconds=.15):
        until = time.monotonic()+seconds
        return Wait(lambda: time.monotonic() >= until, "Waiting for Qt event delivery")

    def screenshot(self, name, widget=None):
        path = self.output / (self.config["run_id"]+"-"+name+".png")
        target = widget or aqt.mw
        if target and target.grab().save(str(path)):
            self.report["screenshots"].append(path.name)

    def js(self, web, expression):
        box = {}
        web.evalWithCallback(expression, lambda value: box.update(value=value))
        yield Wait(lambda: "value" in box, "Native QWebEngine JavaScript callback")
        return box["value"]

    def wait_js(self, web, expression, description, timeout=40):
        until = time.monotonic()+timeout
        while time.monotonic() < until:
            value = yield from self.js(web, expression)
            if value:
                return value
            yield self.pause()
        raise TimeoutError(description)

    def snapshot(self):
        result = {}
        for identity, note in self.adapter.exercise_notes(aqt.mw.col).items():
            card = note.cards()[0]
            result[identity] = {"note_id": int(note.id), "card_id": int(card.id),
                                "reps": card.reps, "queue": card.queue, "type": card.type,
                                "due": card.due, "interval": card.ivl,
                                "revlog": [list(row) for row in aqt.mw.col.db.all("select id,ease,ivl,lastIvl,type from revlog where cid=? order by id", card.id)]}
        return result

    def dismiss_info(self, substring):
        yield Wait(lambda: self.modal(text=substring) is not None, "Expected information dialog: "+substring)
        dialog = self.modal(text=substring)
        self.report["checks"].append({"dialog": dialog.text()})
        self.schedule(dialog.accept)
        yield Wait(lambda: not visible(dialog), "Close information dialog")

    def file_dialog(self, filename, save=False):
        yield Wait(lambda: self.modal() is not None and any(isinstance(w, QFileDialog) and w.isVisible()
                        for w in QApplication.topLevelWidgets()), "Native Qt file chooser")
        dialog = next(w for w in QApplication.topLevelWidgets() if isinstance(w, QFileDialog) and w.isVisible())
        dialog.setDirectory(str(Path(filename).parent))
        dialog.selectFile(str(filename))
        name = dialog.findChild(QLineEdit, "fileNameEdit")
        if name:
            name.setText(str(filename))
        self.screenshot("file-chooser", dialog)
        standard = QDialogButtonBox.StandardButton.Save if save else QDialogButtonBox.StandardButton.Open
        accept_button = next((box.button(standard) for box in dialog.findChildren(QDialogButtonBox)
                              if box.button(standard) is not None), None)
        assert accept_button is not None and accept_button.isEnabled(), "Native file chooser approval button"
        self.schedule(lambda: QTest.mouseClick(accept_button, Qt.MouseButton.LeftButton))
        yield Wait(lambda: not any(isinstance(w, QFileDialog) and w.isVisible()
                                  for w in QApplication.topLevelWidgets()), "Accept native Qt file chooser")

    def steps(self):
        mw = aqt.mw
        yield Wait(lambda: mw.col is not None and mw.state == "deckBrowser", "Actual Anki profile startup")
        if self.config["phase"] == "install":
            from aqt.addons import InstallOk
            result = mw.addonManager.install(self.config["addon_path"], force_enable=True)
            assert isinstance(result, InstallOk) and result.compatible, repr(result)
            installed = Path(mw.addonManager.addonsFolder(self.config["package"]))
            assert (installed/"__init__.py").is_file()
            installed_provenance = json.loads((installed / "provenance.json").read_text(encoding="utf-8"))
            assert installed_provenance["source_commit"] == self.config["source_commit"]
            assert installed_provenance["source_tree_sha256"] == self.config["source_tree_sha256"]
            assert hashlib.sha256(Path(self.config["addon_path"]).read_bytes()).hexdigest() == self.config["package_sha256"]
            for name, digest in installed_provenance["source_files"].items():
                assert hashlib.sha256((installed / name).read_bytes()).hexdigest() == digest, name
            self.report["checks"].append("Official AddonManager installed the exact .ankiaddon; next launch loads it normally")
            self.report["installed_package"] = installed.name
            return

        self.ui = importlib.import_module(self.config["package"]+".ui")
        self.adapter = importlib.import_module(self.config["package"]+".collection")
        yield Wait(lambda: self.ui._controller is not None and not self.ui._controller.closed,
                   "Packaged COMULS profile hook created its real controller")
        self.c = self.ui._controller
        yield Wait(lambda: not self.c.busy and getattr(self.c, "media_ready", True),
                   "Bundled collection media installation")
        assert self.c.media_ready, "Bundled media must finish verification before study"
        actions = [a for a in mw.form.menuTools.actions() if a.text().replace("&", "") == "COMULS"]
        assert len(actions) == 1, "COMULS Tools action must be installed exactly once"
        self.schedule(actions[0].trigger)
        yield Wait(lambda: self.c.window is not None and self.c.window.isVisible(), "Actual COMULS course window")
        window = self.c.window
        assert window.tabs.count() == 6
        self.screenshot("course", window)
        if self.config["phase"] == "reopen":
            previous = json.loads(Path(self.config["previous_report"]).read_text(encoding="utf-8"))
            assert self.snapshot() == previous["native_snapshot"], "Native note/card/review history changed across application restart"
            assert self.c.state()["stage"] == previous["stage"]
            assert self.c.state()["manager_id"] == previous["manager_id"]
            assert self.c.state()["budget_minutes"] == previous["budget_minutes"]
            for identity, explanation in previous.get("updated_explanations", {}).items():
                assert self.c.by_id[identity]["explanation"] == explanation, "Imported pack did not persist across restart"
            self.report["checks"].append("Full application shutdown/reopen preserved stage, settings, manager, note/card IDs, scheduler state and revlog")
            self.report["native_snapshot"] = self.snapshot()
            return

        state = self.c.state()
        assert not state["stage_confirmed"], "A fresh profile must require explicit entry level"
        assert state["budget_minutes"] == 15
        assert window.tabs.currentIndex() == 1
        if self.config.get("suggested_cohort"):
            assert window.stage_box.currentText() == self.config["suggested_cohort"], "Cohort package must suggest its entry level on a fresh profile"
        self.report["fsrs_initial"] = mw.col.get_config("fsrs", False)
        window.stage_box.setCurrentText(self.config["stage"])
        self.click(window, "Use this level")
        yield Wait(lambda: not self.c.busy and self.c.state().get("stage_confirmed")
                   and self.c.state()["stage"] == self.config["stage"], "Native CollectionOp entry-level confirmation")
        window.tabs.setCurrentIndex(4)
        window.minutes.setValue(20)
        window.diagnostics.setChecked(True)
        self.click(window, "Save settings")
        yield Wait(lambda: self.c.state()["budget_minutes"] == 20 and self.c.state().get("diagnostics"), "Saved actual Settings controls")
        self.report["checks"].append("Explicit stage selection and persisted Settings controls")
        window.tabs.setCurrentIndex(0)

        begins, ends = len(self.report["audio"]), self.ends
        self.click(window, "Check French audio")
        yield Wait(lambda: self.modal("French audio check") is not None, "Bundled French audio check")
        yield Wait(lambda: self.recording_completed_since(begins),
                   "Real native audio player begins and completes bundled French check", 60)
        dialog = self.modal("French audio check")
        yes = dialog.button(QMessageBox.StandardButton.Yes)
        yield Wait(lambda: yes.isEnabled(), "French audio confirmation available after real playback")
        self.schedule(yes.click)
        yield Wait(lambda: self.c.state()["audio_confirmed"] and not visible(dialog), "Saved French audio confirmation")
        self.report["checks"].append("French audio used a real native player to completion; no French system voice or fake player")
        assert all(a["tag"] == "SoundOrVideoTag" for a in self.report["audio"]), "Demo must use packaged recording audio"

        if self.config.get("extra_controls"):
            before = self.snapshot()
            self.click(window, "Try the card controls")
            yield Wait(lambda: self.modal("Try the four card controls") is not None, "Optional four-shell onboarding")
            tutorial = self.modal("Try the four card controls")
            tabs = tutorial.findChildren(QTabWidget)
            assert len(tabs) == 1 and tabs[0].count() == 4
            for index in range(4):
                tabs[0].setCurrentIndex(index)
                panel = tabs[0].currentWidget()
                if index == 0:
                    self.click(panel, "Show answer")
                elif index == 1:
                    panel.findChildren(QLineEdit)[0].setText("bonjour")
                    self.click(panel, "Check")
                elif index == 2:
                    self.click(panel, "Thank you")
                else:
                    for word in ("Je", "suis", "étudiant"):
                        self.click(panel, word)
                        yield self.pause(.1)
                yield self.pause(.4)
                from aqt.qt import QLabel
                labels = [w.text() for w in panel.findChildren(QLabel)]
                assert any(("Hello" in value if index == 0 else "Correct" in value if index in (1,2)
                            else value == "Je suis étudiant") for value in labels), labels
                self.screenshot("onboarding-"+str(index), tutorial)
            self.click(tutorial, "Done")
            yield Wait(lambda: not visible(tutorial), "Close four-shell onboarding")
            assert self.snapshot() == before, "Ungraded control tutorial must not create or grade cards"
            self.report["checks"].append("All four optional onboarding shells remain ungraded")
            window.tabs.setCurrentIndex(2)
            window.search.setText("meaning")
            if window.library.count() == 0:
                window.search.clear()
            window.library.setCurrentRow(0)
            self.click(window, "Open selected reference")
            yield Wait(lambda: self.modal("library") is not None, "Ungraded library reference")
            reference = self.modal("library")
            self.screenshot("reference", reference)
            self.click(reference, "Close")
            yield Wait(lambda: not visible(reference), "Close library reference")
            assert self.snapshot() == before, "Library preview must not admit or grade"
            self.report["checks"].append("Library search/reference remains ungraded")
            window.tabs.setCurrentIndex(0)

        for kind in self.config["types"]:
            before = set(self.adapter.exercise_notes(mw.col))
            index = window.activity.findData(kind)
            assert index >= 0
            window.activity.setCurrentIndex(index)
            self.click(window, "Prepare one new exercise")
            yield Wait(lambda: self.c.prepare_dialog is not None and visible(self.c.prepare_dialog),
                       "Supported familiarisation dialog for "+kind)
            preparation = self.c.prepare_dialog
            checkboxes = preparation.findChildren(QCheckBox)
            assert len(checkboxes) == 1 and not checkboxes[0].isChecked()
            audio_buttons = [b for b in preparation.findChildren(QPushButton) if b.text() == "Hear the whole sentence"]
            if audio_buttons:
                begins, ends = len(self.report["audio"]), self.ends
                self.click(preparation, "Hear the whole sentence")
                yield Wait(lambda: self.recording_completed_since(begins),
                           "Real familiarisation recording playback for "+kind, 60)
            # This test student explicitly recognises the displayed baseline
            # carrier uses. New understanding is never inserted into state.
            for choice in preparation.findChildren(QComboBox):
                if choice.objectName().startswith("support_"):
                    choice.setCurrentIndex(choice.findData("known"))
            contrast_buttons = [b.text() for b in preparation.findChildren(QPushButton)
                                if b.text().startswith("Hear “")]
            for label in contrast_buttons:
                begins, ends = len(self.report["audio"]), self.ends
                self.click(preparation, label)
                yield Wait(lambda: self.recording_completed_since(begins),
                           "Real contrast-option preparation recording: " + label, 60)
            checkboxes[0].setChecked(True)
            self.screenshot("prepare-"+kind, preparation)
            self.click(preparation, "Add to Anki practice")
            yield Wait(lambda: self.c.prepare_dialog is None and not self.c.busy
                       and len(set(self.adapter.exercise_notes(mw.col))-before) == 1, "Native admission completes for "+kind)
            identity = (set(self.adapter.exercise_notes(mw.col))-before).pop()
            note = self.adapter.exercise_notes(mw.col)[identity]
            ns = self.adapter.note_state(note)
            assert ns["lifecycle"] == "admitted" and ns["familiarised_day"] == str(mw.col.sched.today)
            assert note.cards()[0].queue >= 0 and note.cards()[0].reps == 0
            assert self.adapter.note_payload(note)["type"] == kind
            self.report["checks"].append({"familiarised_and_admitted": identity, "type": kind})

        if self.config.get("verify_caps"):
            assert self.c.budget()["new_units"] == 6
            before = self.snapshot()
            window.activity.setCurrentIndex(0)
            self.click(window, "Prepare one new exercise")
            yield from self.dismiss_info("No new card")
            assert self.snapshot() == before
            self.report["six_unit_cap_verified"] = True

        admitted = self.adapter.exercise_notes(mw.col)
        pending = set(admitted)
        self.click(window, "Study due / new cards in Anki")
        yield Wait(lambda: mw.state == "overview", "Native Anki overview")
        yield from self.wait_js(mw.web, "!!document.querySelector('#study')", "Native Study Now button")
        yield from self.js(mw.web, "document.querySelector('#study').click(); true")
        yield Wait(lambda: mw.state == "review" and mw.reviewer.card is not None, "Native Anki Reviewer")
        while pending:
            yield Wait(lambda: mw.state == "review" and mw.reviewer.state == "question"
                       and self.c.reviewer.expected is not None and self.c.reviewer.expected["exercise_id"] in pending,
                       "Native scheduler selected the next unreviewed admitted card")
            identity = self.c.reviewer.expected["exercise_id"]
            note = self.adapter.exercise_notes(mw.col)[identity]
            exercise = self.adapter.note_payload(note)
            card_id = int(note.cards()[0].id)
            assert not mw.reviewer.auto_advance_enabled
            yield from self.wait_js(mw.web, "document.querySelector('.comuls-card[data-comuls-side=front][data-comuls-mounted=true]') !== null",
                                    "Actual rendered COMULS front")
            self.screenshot("front-"+exercise["type"], mw)
            if exercise.get("audio_file"):
                if exercise["type"] == "sentence_reconstruction":
                    hidden = yield from self.js(mw.web, "document.querySelector('.comuls-tile-stage').hidden && document.querySelector('.comuls-primary').disabled")
                    assert hidden, "Reconstruction word tiles must stay hidden until listening finishes"
                begins = len(self.report["audio"])
                played = yield from self.js(mw.web, "(function(){var b=document.querySelector('.comuls-audio .replay-button,.comuls-audio a'); if(!b)return false; b.click();return true;})()")
                assert played, "Native recording replay control is missing"
                yield Wait(lambda: len(self.report["audio"]) > begins, "Native QWebEngine audio replay reaches real player")
                if exercise["type"] == "sentence_reconstruction":
                    yield Wait(lambda: self.recording_completed_since(begins), "Complete native listening unlocks reconstruction", 60)
                    yield from self.wait_js(mw.web, "!document.querySelector('.comuls-tile-stage').hidden && !document.querySelector('.comuls-primary').disabled",
                                            "Only completed native playback reveals reconstruction tiles")
                    assert not self.c.reviewer.target_hint, "Completed listening is not an answer-revealing help action"
            if self.config.get("extra_controls") and not self.report["reviews"]:
                supported = yield from self.js(mw.web, "(function(){var b=Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Meaning support');if(b){b.click();return true;}return false;})()")
                if supported:
                    yield Wait(lambda: self.c.reviewer.carrier_help, "Actual carrier support bridge")
            answer = json.dumps(exercise["answer"], ensure_ascii=False)
            selected = json.dumps(next((o["id"] for o in exercise.get("choices", []) if o.get("correct")), None))
            tokens = json.dumps(exercise.get("tokens") or [{"id": "token-"+str(i), "text": word}
                               for i, word in enumerate(exercise["answer"].split())], ensure_ascii=False)
            script = """(function(){
                var p=JSON.parse(document.getElementById('comuls-data').textContent), shell=COMULSCard.shellFor(p);
                if(shell==='typed'){var i=document.getElementById('comuls-response');i.value=ANSWER;i.dispatchEvent(new Event('input',{bubbles:true}));}
                if(shell==='choice'){var b=Array.from(document.querySelectorAll('[data-choice-id]')).find(b=>b.getAttribute('data-choice-id')===String(CHOICE));if(!b)return false;b.click();}
                if(shell==='tiles'){TOKENS.forEach(function(t){var b=Array.from(document.querySelectorAll('.comuls-tile-bank button')).find(b=>!b.disabled&&b.textContent===t.text);if(!b)throw new Error('Missing tile');b.click();});}
                var check=document.querySelector('.comuls-primary');check.click();check.click();return shell;
            })()""".replace("ANSWER", answer).replace("CHOICE", selected).replace("TOKENS", tokens)
            shell = yield from self.js(mw.web, script)
            assert shell in ("typed", "choice", "tiles", "reveal")
            yield Wait(lambda: mw.reviewer.state == "answer" and self.c.reviewer.latch.submitted and not self.c.reviewer.busy,
                       "DOM submission, nonce bridge, answer exposure CollectionOp")
            feedback = yield from self.wait_js(mw.web, "document.querySelector('.comuls-feedback') && document.querySelector('.comuls-feedback').getAttribute('data-status')",
                                              "Rendered reference feedback")
            assert feedback == ("self_compare" if exercise["type"] == "meaning_recall" else "correct"), feedback
            assert mw.col.db.scalar("select count(*) from revlog where cid=?", card_id) == 0, "Front checks must not grade"
            self.screenshot("answer-"+exercise["type"], mw)
            if self.config.get("extra_controls") and not self.report["reviews"]:
                yield from self.js(mw.web, "Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Report this card').click(); true")
                yield Wait(lambda: any(e.get("event") == "report" for e in self.c.local.events()), "Real card report reaches local telemetry")
            # Use every real rating; place short-interval ratings later so the
            # format sweep normally finishes before an Again card becomes due.
            ease = (3, 4, 2, 1)[len(self.report["reviews"]) % 4]
            selector = "[data-ease='"+str(ease)+"']"
            yield from self.wait_js(mw.bottomWeb, "!!document.querySelector("+json.dumps(selector)+")", "Native learner rating button")
            yield from self.js(mw.bottomWeb, "document.querySelector("+json.dumps(selector)+").click(); true")
            yield Wait(lambda: mw.col.get_card(card_id).reps == 1 and mw.col.db.scalar("select count(*) from revlog where cid=?", card_id) == 1,
                       "Native learner-selected grade and authoritative revlog")
            self.report["reviews"].append({"exercise_id": identity, "type": exercise["type"], "level": exercise["level"],
                                           "shell": shell, "card_id": card_id, "ease": ease, "feedback": feedback})
            pending.remove(identity)

        self.schedule(lambda: mw.moveToState("deckBrowser"))
        yield Wait(lambda: mw.state == "deckBrowser", "Exit native review")
        self.c.show()
        before_undo = self.snapshot()
        final_identity = self.report["reviews"][-1]["exercise_id"]
        card_id = before_undo[final_identity]["card_id"]
        yield Wait(lambda: mw.form.actionUndo.isEnabled(), "Native Undo menu enabled")
        self.schedule(mw.form.actionUndo.trigger)
        yield Wait(lambda: mw.col.get_card(card_id).reps == 0 and mw.col.db.scalar("select count(*) from revlog where cid=?", card_id) == 0,
                   "Native Undo restores card state and removes authoritative review")
        yield Wait(lambda: mw.form.actionRedo.isEnabled(), "Native Redo menu enabled")
        self.schedule(mw.form.actionRedo.trigger)
        yield Wait(lambda: self.snapshot() == before_undo, "Native Redo restores exact native card history")
        self.report["checks"].append("Native Undo/Redo via Anki menu restored exact scheduling state and revlog")

        if self.config.get("extra_controls"):
            stage_before = self.c.state()["stage"]
            original = self.snapshot()
            window.tabs.setCurrentIndex(1)
            for stage in (("B2" if stage_before == "B1" else "B1"), stage_before):
                window.tabs.setCurrentIndex(1)
                window.stage_box.setCurrentText(stage)
                self.click(window, "Use this level")
                yield Wait(lambda: not self.c.busy and self.c.state()["stage"] == stage, "Real cohort change preserves reviews")
                assert self.snapshot() == original, "A cohort change modified already-reviewed native cards"
            self.report["checks"].append("B1/B2 UI cohort changes preserve reviewed native IDs, scheduling and revlog")
            yield from self.content_update_and_export(final_identity)

        self.c.flush_time()
        self.report["native_snapshot"] = self.snapshot()
        state = self.c.state()
        self.report["manager_id"] = state["manager_id"]
        self.report["budget_minutes"] = state["budget_minutes"]
        self.report["checks"].append({"active_seconds": self.c.budget()["active_seconds"],
                                      "new_units": self.c.budget()["new_units"],
                                      "native_due": self.adapter.stats(mw.col)["due"]})
        assert self.c.budget()["active_seconds"] > 0, "Real foreground review/preparation must register study time"
        assert mw.col.get_config("fsrs", False) == self.report["fsrs_initial"], "COMULS must leave the native FSRS setting untouched"
        assert len(self.report["reviews"]) == len(self.config["types"])
        assert all(mw.col.get_card(r["card_id"]).reps == 1 for r in self.report["reviews"])

    def content_update_and_export(self, identity):
        window = self.c.window
        before = self.snapshot()
        exercise = copy.deepcopy(self.c.by_id[identity])
        exercise["explanation"] += " Editorial import verified in the disposable end-to-end profile."
        update = {"schema_version": 1, "pack_id": "e2e-editorial-update", "version": "1",
                  "exercises": [exercise]}
        path = self.output / (self.config["run_id"]+"-editorial-pack.json")
        path.write_text(json.dumps(update, ensure_ascii=False), encoding="utf-8")
        window.tabs.setCurrentIndex(4)
        installers = [b for b in window.findChildren(QPushButton) if "Install course pack" in b.text() and b.isVisible()]
        if installers:
            self.schedule(installers[0].click)
        else:
            self.click(window, "content", contains=True)
            yield Wait(lambda: any(isinstance(w, QDialog) and w.isVisible() and w is not window
                                   and any("Install" in b.text() for b in w.findChildren(QPushButton))
                                   for w in QApplication.topLevelWidgets()), "Actual content manager")
            manager = next(w for w in QApplication.topLevelWidgets() if isinstance(w, QDialog) and w.isVisible()
                           and w is not window and any("Install" in b.text() for b in w.findChildren(QPushButton)))
            buttons = [b for b in manager.findChildren(QPushButton) if "Install" in b.text() and b.isVisible()]
            assert len(buttons) == 1
            listing = manager.findChildren(importlib.import_module("aqt.qt").QListWidget)[0]
            from aqt.qt import Qt
            for row in range(listing.count()):
                if listing.item(row).data(Qt.ItemDataRole.UserRole) == identity:
                    listing.setCurrentRow(row)
                    break
            else:
                raise AssertionError("Managed native card missing from content manager")
            self.click(manager, "Pause selected")
            yield Wait(lambda: not self.c.busy and aqt.mw.col.get_card(before[identity]["card_id"]).queue == -1,
                       "Actual managed pause suspends native card")
            paused = self.snapshot()[identity]
            assert all(paused[key] == before[identity][key] for key in before[identity] if key != "queue")
            self.click(manager, "Restore selected")
            yield Wait(lambda: not self.c.busy and self.snapshot() == before, "Managed restore preserves native schedule and history")
            self.report["checks"].append("Content-manager pause/restore changes only the owned pause, preserving native history")
            self.schedule(buttons[0].click)
        yield from self.file_dialog(path)
        yield Wait(lambda: self.modal("Review course update") is not None, "Concrete declarative course update preflight")
        preflight = self.modal("Review course update")
        assert preflight.button(QMessageBox.StandardButton.No).isDefault(), "Course import must default to keeping current content"
        assert self.snapshot() == before, "Preflight must not change native collection data"
        self.screenshot("course-update-preflight", preflight)
        self.schedule(lambda: QTest.mouseClick(preflight.button(QMessageBox.StandardButton.Yes), Qt.MouseButton.LeftButton))
        yield Wait(lambda: not visible(preflight), "Approve concrete editorial import in real dialog")
        yield Wait(lambda: not self.c.busy and self.c.by_id[identity]["explanation"] == exercise["explanation"],
                   "Declarative content update completes through real native CollectionOp")
        if self.modal(text="Pack installed"):
            yield from self.dismiss_info("Pack installed")
        else:
            # The content manager can report success inline instead of a message box.
            yield self.pause(.3)
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QDialog) and widget.isVisible() and widget is not window:
                self.schedule(widget.accept)
        yield self.pause(.3)
        assert self.snapshot() == before, "Editorial import changed native IDs, schedule or review history"
        self.report["updated_explanations"] = {identity: exercise["explanation"]}
        self.report["checks"].append("Editorial course-pack import preserved exact native note/card identity, schedule and revlog")
        window.tabs.setCurrentIndex(3)
        self.click(window, "Record today's effort / fatigue")
        yield Wait(lambda: self.modal("Today's effort") is not None, "Actual daily effort dialog")
        effort = self.modal("Today's effort")
        from aqt.qt import QComboBox
        boxes = effort.findChildren(QComboBox)
        assert len(boxes) == 1
        boxes[0].setCurrentIndex(3)
        self.click(effort, "Save")
        yield Wait(lambda: not visible(effort) and self.c.state()["days"][str(aqt.mw.col.sched.today)]["fatigue"] == 4,
                   "Daily fatigue persists through actual controls")
        assert self.snapshot() == before
        self.report["checks"].append("Effort/fatigue control saves activity without grading")
        path = self.output / (self.config["run_id"]+"-study-export.json")
        self.click(window, "Export study data…")
        yield from self.file_dialog(path, save=True)
        yield Wait(path.is_file, "Actual export created a study JSON file")
        yield from self.dismiss_info("Study data exported")
        exported = json.loads(path.read_text(encoding="utf-8"))
        assert exported["stage"] == self.config["stage"]
        assert len(exported["cards"]) == len(before)
        assert sum(len(c["reviews"]) for c in exported["cards"]) == len(before)
        assert all("response" not in event for event in exported["events"]), "Optional export must not include raw typed responses"
        self.report["checks"].append("Actual Save dialog export reflects native reviews and excludes raw typed responses")


_driver = None


def install():
    config_path = os.environ.get("COMULS_E2E_CONFIG")
    if not config_path:
        return
    def start():
        global _driver
        if _driver is None:
            _driver = Driver(json.loads(Path(config_path).read_text(encoding="utf-8")))
    gui_hooks.profile_did_open.append(lambda: QTimer.singleShot(150, start))

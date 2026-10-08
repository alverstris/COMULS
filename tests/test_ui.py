"""Headless native Qt UI checks with a real Anki collection.

Only the main-window shell, dialog choices, AV hardware and asynchronous
operation dispatch are controlled by the fixture. Collection reads, writes,
note generation and native scheduling are never mocked.
"""
from __future__ import annotations

import copy
import importlib
import json
import os
import shutil
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import aqt
from aqt.qt import QApplication, QMainWindow, QMenu, QPushButton, QMessageBox
from anki.collection import Collection

PACKAGE = "_comuls_ui_test"
if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(Path(__file__).resolve().parents[1] / "addon")]
    sys.modules[PACKAGE] = package
ui = importlib.import_module(PACKAGE + ".ui")
adapter = importlib.import_module(PACKAGE + ".collection")


@pytest.fixture(scope="module")
def app():
    value = QApplication.instance() or QApplication([])
    yield value


@pytest.fixture
def course(app, tmp_path, monkeypatch):
    col = Collection(str(tmp_path / "ui-collection.anki2"))
    profile = tmp_path / "profile"
    profile.mkdir()

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.col = col
            self.pm = types.SimpleNamespace(profileFolder=lambda: str(profile))
            self.state = "deckBrowser"
            self.reviewer = types.SimpleNamespace(card=None)
            self.form = types.SimpleNamespace(menuTools=QMenu("Tools", self))
            self.addonManager = types.SimpleNamespace(getConfig=lambda *_args: {})
            self.transitions = []

        def moveToState(self, state):
            self.state = state
            self.transitions.append(state)

    window = MainWindow()
    monkeypatch.setattr(ui, "mw", window)
    monkeypatch.setattr(aqt, "mw", window)
    root = tmp_path / "addon-data"
    (root / "data").mkdir(parents=True)
    shutil.copyfile(Path(__file__).resolve().parents[1] / "addon" / "data" / "tester.json",
                    root / "data" / "tester.json")
    monkeypatch.setattr(ui, "ROOT", root)

    audio = {"plays": [], "stops": 0}
    def stop_audio():
        audio["stops"] += 1
    monkeypatch.setattr(ui, "av_player", types.SimpleNamespace(
        play_tags=lambda tags: audio["plays"].extend(tags),
        stop_and_clear_queue=stop_audio))
    messages = []
    monkeypatch.setattr(ui, "showInfo", lambda text, **_kwargs: messages.append(("info", text)))
    monkeypatch.setattr(ui, "showWarning", lambda text, **_kwargs: messages.append(("warning", text)))
    monkeypatch.setattr(ui, "tooltip", lambda *_args, **_kwargs: None)

    registrations = []
    class ReviewerHandle:
        def __init__(self, controller):
            self.controller = controller
            self.closed = False
        def close(self):
            self.closed = True
    reviewer_stub = types.ModuleType(PACKAGE + ".reviewer")
    def register(controller):
        handle = ReviewerHandle(controller)
        registrations.append(handle)
        return handle
    reviewer_stub.register = register
    monkeypatch.setitem(sys.modules, PACKAGE + ".reviewer", reviewer_stub)

    # Run the actual mutating callback and native undo merge on the test's
    # thread. Qt task-manager dispatch is outside this minimal window shell.
    class ImmediateCollectionOp:
        def __init__(self, *, parent, op):
            self.op = op
            self.on_success = None
            self.on_failure = None
        def success(self, callback):
            self.on_success = callback
            return self
        def failure(self, callback):
            self.on_failure = callback
            return self
        def run_in_background(self, **_kwargs):
            try:
                result = self.op(col)
            except Exception as error:
                if self.on_failure:
                    self.on_failure(error)
                else:
                    raise
            else:
                if self.on_success:
                    self.on_success(result)
    monkeypatch.setattr(ui, "CollectionOp", ImmediateCollectionOp)
    controller = ui.CourseController()
    controller._test_messages = messages
    controller._test_audio = audio
    controller._test_registrations = registrations
    controller._test_mw = window
    ui._controller = None
    yield controller
    controller.close()
    if ui._controller is not None and ui._controller is not controller:
        ui._controller.close()
    ui._controller = None
    app.processEvents()
    window.close()
    window.col = None
    col.close()


def show_window(controller):
    window = ui.CourseWindow(controller)
    controller.window = window
    window.refresh()
    return window


def first_text_exercise(controller):
    return next(value for value in controller.catalog
                if value["type"] == "meaning_recall"
                and ui.level_eligible(value, "B1"))


def find_button(window, text):
    return next(button for button in window.findChildren(QPushButton)
                if button.text() == text)


def test_real_qt_course_window_constructs_all_tabs_and_pack_content(course):
    window = show_window(course)
    assert [window.tabs.tabText(index) for index in range(window.tabs.count())] == [
        "Home", "Levels", "Library", "Progress", "Settings", "About"]
    assert len(window.checks) == 13
    assert len(course.catalog) >= 39
    assert window.library.count() == len(course.catalog)
    assert "Entry level B1" in window.summary.text()
    assert course.state()["audio_confirmed"] is False
    assert course.clock.isActive()
    assert len(course._test_registrations) == 1


def test_settings_and_entry_level_buttons_write_real_synced_state(course):
    window = show_window(course)
    window.minutes.setValue(20)
    enabled = list(window.checks)
    window.checks[enabled[-1]].setChecked(False)
    find_button(window, "Save settings").click()
    state = course.state()
    assert state["budget_minutes"] == 20
    assert enabled[-1] not in state["enabled"]
    assert state["manager_id"] == course.local.manager_id
    assert isinstance(state["manager_id"], str)
    window.stage_box.setCurrentText("B2")
    find_button(window, "Use this level").click()
    assert course.state()["stage"] == "B2"
    assert "Entry level B2" in window.summary.text()
    assert not [entry for entry in course._test_messages if entry[0] == "warning"]


def test_prepare_button_creates_paused_card_without_fabricating_familiarity(course, monkeypatch):
    window = show_window(course)
    exposed = []
    monkeypatch.setattr(course, "familiarise", lambda exercise: exposed.append(exercise))
    # Explicit onboarding choice, including confirming the initial B1 route.
    window.stage_box.setCurrentText("B1")
    find_button(window, "Use this level").click()
    assert course.state().get("stage_confirmed") is True
    window.activity.setCurrentIndex(window.activity.findData("meaning_recall"))
    find_button(window, "Prepare one new exercise").click()
    assert len(exposed) == 1
    note = adapter.exercise_notes(course._test_mw.col)[exposed[0]["id"]]
    assert note.cards()[0].queue == -1
    assert adapter.note_state(note)["familiarised_day"] is None
    assert adapter.note_state(note)["admitted_day"] is None
    assert course.budget()["new_units"] == 0
    assert course.budget()["admitted_cards"] == 0


def test_budget_reads_encoded_note_state_and_native_day_without_reset(course):
    col = course._test_mw.col
    exercise = first_text_exercise(course)
    day = col.sched.today
    adapter.prepare_exercise(col, exercise, day)
    adapter.mark_familiarised(col, exercise["id"], day)
    adapter.activate_exercise(col, exercise, day)
    course.add_active_seconds(150)
    course.flush_time()
    budget = course.budget()
    assert budget["new_units"] == 1
    assert budget["admitted_cards"] == 1
    assert budget["active_seconds"] == 150
    assert budget["remaining_seconds"] == 750
    assert exercise["unit_id"] in budget["seen_units"]
    assert course.active_buffer == 0
    assert course.state()["days"][str(day)]["active_seconds"] == 150
    course.flush_time()
    assert course.state()["days"][str(day)]["active_seconds"] == 150


def test_french_audio_check_requires_an_explicit_confirmation(course, monkeypatch):
    responses = [QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes]
    monkeypatch.setattr(QMessageBox, "exec", lambda _self: responses.pop(0))
    assert course.state()["audio_confirmed"] is False
    course.audio_check()
    assert course.state()["audio_confirmed"] is False
    course.audio_check()
    assert course.state()["audio_confirmed"] is True
    assert len(course._test_audio["plays"]) == 2
    assert all(tag.lang == "fr_FR" for tag in course._test_audio["plays"])


def test_pack_install_controls_update_catalog_without_auto_admission(course, tmp_path, monkeypatch):
    show_window(course)
    exercise = copy.deepcopy(first_text_exercise(course))
    exercise["id"] = "ui-pack-extra"
    pack = {"schema_version": 1, "pack_id": "ui-pack", "version": "1",
            "exercises": [exercise]}
    path = tmp_path / "new-pack.json"
    path.write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(ui, "QFileDialog", types.SimpleNamespace(
        getOpenFileName=lambda *_args: (str(path), "JSON (*.json)")))
    monkeypatch.setattr(ui.QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes)
    original_count = len(course.catalog)
    course.install_pack()
    assert len(course.catalog) == original_count + 1
    assert exercise["id"] in course.by_id
    assert course.catalog_path.is_file()
    assert adapter.exercise_notes(course._test_mw.col) == {}
    assert not [entry for entry in course._test_messages if entry[0] == "warning"]


def test_export_uses_native_history_without_answers_personal_notes_or_device_id(
        course, tmp_path, monkeypatch):
    show_window(course)
    col = course._test_mw.col
    exercise = first_text_exercise(course)
    nid = adapter.prepare_exercise(col, exercise, col.sched.today)
    adapter.mark_familiarised(col, exercise["id"], col.sched.today)
    adapter.activate_exercise(col, exercise, col.sched.today)
    note = col.get_note(nid)
    note["PersonalNotes"] = "SECRET_PERSONAL_NOTES"
    col.update_note(note)
    card = note.cards()[0]
    card.start_timer()
    col.sched.answerCard(card, 3)
    course.local.record({"event": "answer_submitted", "exercise_id": exercise["id"],
                         "typed_answer": "SECRET_TYPED_ANSWER",
                         "profile_path": "SECRET_PROFILE_PATH"}, True)
    path = tmp_path / "study-export.json"
    monkeypatch.setattr(ui, "QFileDialog", types.SimpleNamespace(
        getSaveFileName=lambda *_args: (str(path), "JSON (*.json)")))
    course.export()
    text = path.read_text(encoding="utf-8")
    exported = json.loads(text)
    assert exported["cards"][0]["exercise_id"] == exercise["id"]
    assert len(exported["cards"][0]["reviews"]) == len(col.get_review_logs(card.id)) == 1
    assert exported["cards"][0]["reviews"][0]["button_chosen"] == 3
    assert exported["events"][0]["event"] == "answer_submitted"
    for secret in ("SECRET_PERSONAL_NOTES", "SECRET_TYPED_ANSWER", "SECRET_PROFILE_PATH",
                   course.local.manager_id, course._test_mw.pm.profileFolder()):
        assert secret not in text
    assert card.id == col.get_note(nid).cards()[0].id


def test_other_desktop_can_review_but_cannot_claim_admission_silently(course):
    state = course.state()
    state["manager_id"] = "another-desktop-manager"
    adapter.save_state(course._test_mw.col, state)
    assert course.require_manager() is False
    assert course.state()["manager_id"] == "another-desktop-manager"
    assert course.is_manager() is False
    assert adapter.exercise_notes(course._test_mw.col) == {}


def test_controller_close_stops_owned_clock_audio_and_reviewer_once(course):
    handle = course._test_registrations[0]
    course.add_active_seconds(10)
    course.close()
    first_stops = course._test_audio["stops"]
    assert course.closed
    assert not course.clock.isActive()
    assert handle.closed
    assert course.active_buffer == 0
    course.close()
    assert course._test_audio["stops"] == first_stops


def test_first_open_requests_an_explicit_entry_route(course):
    assert not course.state().get("stage_confirmed", False)
    course.show()
    assert course.window.tabs.tabText(course.window.tabs.currentIndex()) == "Levels"
    assert adapter.exercise_notes(course._test_mw.col) == {}
    course.window.stage_box.setCurrentText("B1")
    find_button(course.window, "Use this level").click()
    assert course.state()["stage_confirmed"] is True


def test_profile_lifecycle_and_repeated_menu_open_keep_one_active_reviewer(course):
    ui._controller = course
    ui.open_comuls()
    first_window = course.window
    ui.open_comuls()
    assert ui._controller is course
    assert course.window is first_window
    assert len(course._test_registrations) == 1
    ui.on_profile_close()
    assert ui._controller is None
    assert course.closed
    assert not course.clock.isActive()
    assert course._test_registrations[0].closed

    ui.on_profile_open()
    current = ui._controller
    assert current is not None and current is not course
    assert current.clock.isActive()
    assert sum(not handle.closed for handle in course._test_registrations) == 1
    ui.open_comuls()
    ui.open_comuls()
    assert ui._controller is current
    assert sum(not handle.closed for handle in course._test_registrations) == 1
    ui.on_profile_close()
    assert not current.clock.isActive()
    assert sum(not handle.closed for handle in course._test_registrations) == 0

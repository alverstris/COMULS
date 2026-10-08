"""Bridge boundary tests run without Anki or Qt."""
import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

PATH = Path(__file__).resolve().parents[1] / "addon" / "bridge.py"
SPEC = importlib.util.spec_from_file_location("comuls_bridge_for_tests", PATH)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)

EXPECTED = {"nonce": "fresh-nonce", "card_id": 123, "exercise_id": "exercise-1"}


def message(event="attempt", **changes):
    value = dict(EXPECTED, event=event)
    if event == "attempt":
        value.update(response="réfrigérateur", selected_ids=[], submitted=True,
                     target_hint=False, carrier_help=False, replays=0)
    elif event == "hint":
        value.update(kind="target", reveals_target=True)
    value.update(changes)
    return bridge.PREFIX + json.dumps(value, ensure_ascii=False)


class BridgeTests(unittest.TestCase):
    def test_accepts_current_submission(self):
        event = bridge.validate_message(message(), EXPECTED)
        self.assertEqual(event["response"], "réfrigérateur")

    def test_stale_nonce_wrong_card_and_exercise_are_rejected(self):
        for changes in ({"nonce": "old"}, {"card_id": 124},
                        {"exercise_id": "different"}, {"card_id": "123"},
                        {"card_id": True}):
            with self.subTest(changes=changes):
                self.assertIsNone(bridge.validate_message(message(**changes), EXPECTED))

    def test_oversize_counts_utf8_bytes(self):
        text = message(response="é" * 4000)
        self.assertLess(len(text), 8192)
        self.assertIsNone(bridge.validate_message(text, EXPECTED))

    def test_unsupported_namespace_event_fields_and_malformed_json(self):
        bad = [
            "ans", "other:" + message()[len(bridge.PREFIX):], "comuls:{",
            message(event="grade"), message(ease=4), "comuls:[]",
            message(response={"text": "answer"}),
            message(replays=True), message(replays=-1),
            message(target_hint="false"), message(submitted=False),
            message(selected_ids=["tile", "tile"]),
            message(selected_ids=[{}]),
        ]
        for text in bad:
            with self.subTest(text=text[:80]):
                self.assertIsNone(bridge.validate_message(text, EXPECTED))

    def test_duplicate_json_keys_and_nonfinite_json_are_rejected(self):
        original = message()
        duplicate = original[:-1] + ', "card_id": 123}'
        nonfinite = original.replace('"replays": 0', '"replays": NaN')
        self.assertIsNone(bridge.validate_message(duplicate, EXPECTED))
        self.assertIsNone(bridge.validate_message(nonfinite, EXPECTED))

    def test_auxiliary_events_have_bounded_fields(self):
        for event in ("hint", "replay", "report", "skip"):
            self.assertIsNotNone(bridge.validate_message(message(event), EXPECTED))
        self.assertIsNone(bridge.validate_message(message("hint", reveals_target=False), EXPECTED))
        self.assertIsNone(bridge.validate_message(message("report", reason="x" * 201), EXPECTED))
        self.assertIsNone(bridge.validate_message(message("replay", side="browser"), EXPECTED))

    def test_context_identity_and_live_card_are_required(self):
        class Reviewer:
            def __init__(self, card_id):
                self.card = SimpleNamespace(id=card_id)
        live = Reviewer(123)
        self.assertTrue(bridge.context_matches(live, live, Reviewer, 123))
        self.assertFalse(bridge.context_matches(Reviewer(123), live, Reviewer, 123))
        self.assertFalse(bridge.context_matches(SimpleNamespace(card=live.card), live, Reviewer, 123))
        self.assertFalse(bridge.context_matches(live, live, Reviewer, 124))
        live.card = None
        self.assertFalse(bridge.context_matches(live, live, Reviewer, 123))

    def test_front_and_back_duplicate_submission_counts_once(self):
        latch = bridge.SubmissionLatch()
        latch.reset(EXPECTED["nonce"])
        attempt = bridge.validate_message(message(), EXPECTED)
        self.assertTrue(latch.accept(attempt))
        self.assertFalse(latch.accept(attempt))
        self.assertFalse(latch.accept(dict(attempt, nonce="stale")))
        latch.reset("next-nonce")
        self.assertTrue(latch.accept(dict(attempt, nonce="next-nonce")))

class ReviewerHookTests(unittest.TestCase):
    """Small native-hook fakes exercise lifecycle rules without an Anki install."""

    @classmethod
    def setUpClass(cls):
        import sys
        from types import ModuleType

        cls.saved_modules = {}
        for name in ("aqt", "aqt.operations", "aqt.reviewer", "aqt.sound", "aqt.qt",
                     "comuls_review_tests", "comuls_review_tests.bridge",
                     "comuls_review_tests.core", "comuls_review_tests.reviewer",
                     "comuls_review_tests.collection"):
            cls.saved_modules[name] = sys.modules.get(name)
        package = ModuleType("comuls_review_tests")
        package.__path__ = [str(PATH.parent)]
        sys.modules[package.__name__] = package
        sys.modules["comuls_review_tests.bridge"] = bridge

        core_spec = importlib.util.spec_from_file_location(
            "comuls_review_tests.core", PATH.parent / "core.py")
        core = importlib.util.module_from_spec(core_spec)
        sys.modules[core_spec.name] = core
        core_spec.loader.exec_module(core)

        class NativeReviewer:
            def __init__(self):
                self.card = None
                self.auto_advance_enabled = False
                self.auto_calls = 0
                self.next_calls = 0
                self.web = object()

            def auto_advance_if_enabled(self):
                self.auto_calls += 1

            def nextCard(self):
                self.next_calls += 1

            def toggle_auto_advance(self):
                self.auto_advance_enabled = not self.auto_advance_enabled

        class FakeCollectionOp:
            latest = None

            def __init__(self, parent, op):
                self.op = op
                self.success_callback = None
                self.failure_callback = None
                self.initiator = None
                type(self).latest = self

            def success(self, callback):
                self.success_callback = callback
                return self

            def failure(self, callback):
                self.failure_callback = callback
                return self

            def run_in_background(self, *, initiator=None):
                self.initiator = initiator

        aqt_module = ModuleType("aqt")
        names = ("card_will_show", "webview_did_receive_js_message",
                 "reviewer_did_show_question", "reviewer_did_show_answer",
                 "reviewer_will_answer_card", "reviewer_did_answer_card",
                 "reviewer_will_end", "state_shortcuts_will_change",
                 "reviewer_will_show_context_menu", "audio_will_replay")
        aqt_module.gui_hooks = SimpleNamespace(**{name: [] for name in names})
        aqt_module.mw = None
        operations = ModuleType("aqt.operations")
        operations.CollectionOp = FakeCollectionOp
        reviewer_module = ModuleType("aqt.reviewer")
        reviewer_module.Reviewer = NativeReviewer
        sound = ModuleType("aqt.sound")
        sound.av_player = SimpleNamespace(stop_and_clear_queue=lambda: None)
        qt = ModuleType("aqt.qt")
        qt.QKeySequence = lambda value: value
        for module in (aqt_module, operations, reviewer_module, sound, qt):
            sys.modules[module.__name__] = module
        spec = importlib.util.spec_from_file_location(
            "comuls_review_tests.reviewer", PATH.parent / "reviewer.py")
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)
        cls.aqt = aqt_module
        cls.NativeReviewer = NativeReviewer
        cls.FakeCollectionOp = FakeCollectionOp

    @classmethod
    def tearDownClass(cls):
        import sys
        for name, original in cls.saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

    def setUp(self):
        import html
        self.events = []
        self.errors = []
        self.controller = SimpleNamespace(on_event=self.events.append,
                                          content_error=self.errors.append)
        self.reviewer = self.NativeReviewer()
        self.aqt.mw = SimpleNamespace(state="review", reviewer=self.reviewer)
        self.exercise = {
            "id": "exercise-1", "type": "french_form_recall", "level": "B1",
            "entry_levels": ["B1"], "prompt": "Write the French noun.",
            "answer": "réfrigérateur", "accepted": [], "unit_id": "fridge",
            "prerequisites": [], "exposure_groups": [],
            "qa": {"ready": True}, "provenance": {"kind": "original"},
        }
        self.note = {"COMULS_ID": self.exercise["id"],
                     "Payload": html.escape(json.dumps(self.exercise))}
        self.card = SimpleNamespace(id=123, nid=321, note=lambda: self.note)
        self.reviewer.card = self.card
        self.integration = self.module.ReviewerIntegration(self.controller)

    def begin(self):
        return self.integration._card_will_show("<main>template</main>", self.card,
                                                "reviewQuestion")

    def current_message(self, **changes):
        value = dict(self.integration.expected, event="attempt",
                     response="réfrigérateur", selected_ids=[], submitted=True,
                     target_hint=False, carrier_help=False, replays=0)
        value.update(changes)
        return bridge.PREFIX + json.dumps(value)

    def test_preview_is_inert_and_nonce_precedes_both_scripts(self):
        self.assertEqual(self.integration._card_will_show("preview", self.card,
                                                         "previewQuestion"), "preview")
        self.assertIsNone(self.integration.expected)
        front = self.begin()
        nonce = self.integration.expected["nonce"]
        back = self.integration._card_will_show("<main>back</main>", self.card, "reviewAnswer")
        self.assertTrue(front.startswith("<script>window.comulsContext="))
        self.assertIn(nonce, back)
        self.assertEqual(self.integration.expected["nonce"], nonce)

    def test_auto_guard_preserves_manual_no_attempt_grading(self):
        self.reviewer.auto_advance_enabled = True
        self.begin()
        self.assertFalse(self.reviewer.auto_advance_enabled)
        self.assertEqual(self.integration._will_answer_card((True, 3),
                                                           self.reviewer, self.card), (True, 3))
        self.reviewer.auto_advance_enabled = True
        self.assertEqual(self.integration._will_answer_card((True, 3),
                                                           self.reviewer, self.card), (False, 3))
        self.assertFalse(self.reviewer.auto_advance_enabled)
        self.integration._will_end()
        self.assertTrue(self.reviewer.auto_advance_enabled)

    def test_context_checked_before_parsing_and_own_malformed_consumed(self):
        from unittest.mock import patch
        self.begin()
        foreign = self.NativeReviewer()
        foreign.card = self.card
        with patch.object(self.module, "validate_message",
                          side_effect=AssertionError("Should not parse")):
            self.assertEqual(self.integration._web_message((False, None),
                                                           "comuls:{", foreign), (True, None))
            self.reviewer.card = SimpleNamespace(id=124)
            self.assertEqual(self.integration._web_message((False, None),
                                                           "comuls:{", self.reviewer), (True, None))
        self.assertEqual(self.integration._web_message((False, "prior"), "other:event",
                                                       self.reviewer), (False, "prior"))

    def test_duplicate_attempts_count_once_and_metadata_omits_raw_response(self):
        self.begin()
        text = self.current_message()
        self.integration._web_message((False, None), text, self.reviewer)
        self.integration._web_message((False, None), text, self.reviewer)
        attempts = [event for event in self.events if event["event"] == "attempt"]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["outcome"], "correct")
        self.assertNotIn("response", attempts[0])
        self.assertNotIn("selected_ids", attempts[0])
        self.integration._did_answer_card(self.reviewer, self.card, 3)
        grade = self.events[-1]
        self.assertEqual(grade["event"], "native_grade")
        self.assertEqual(grade["ease"], 3)
        self.assertNotIn("response", grade)

    def test_busy_blocks_grading_but_keeps_safe_attempt_capture(self):
        self.begin()
        self.integration.busy = True
        self.integration._web_message((False, None), self.current_message(), self.reviewer)
        self.assertTrue(self.integration.latch.submitted)
        self.assertEqual(self.integration._will_answer_card((True, 3),
                                                           self.reviewer, self.card), (False, 3))

    def test_skip_advances_only_after_successful_native_bury(self):
        self.begin()
        self.integration._skip_current()
        operation = self.FakeCollectionOp.latest
        self.assertEqual(self.reviewer.next_calls, 0)
        self.assertTrue(self.integration.busy)
        calls = []
        fake_col = SimpleNamespace(sched=SimpleNamespace(
            bury_cards=lambda ids, manual: calls.append((ids, manual))))
        operation.op(fake_col)
        self.assertEqual(calls, [([123], True)])
        self.assertIs(operation.initiator, self.reviewer)
        operation.success_callback(None)
        self.assertEqual(self.reviewer.next_calls, 1)
        self.assertIsNone(self.integration.expected)

    def test_stale_skip_completion_does_not_advance_another_card(self):
        self.begin()
        self.integration._skip_current()
        operation = self.FakeCollectionOp.latest
        self.reviewer.card = SimpleNamespace(id=124)
        operation.success_callback(None)
        self.assertEqual(self.reviewer.next_calls, 0)

    def test_shortcut_auto_block_is_runtime_specific_to_comuls(self):
        shortcuts = [("Shift+A", self.reviewer.toggle_auto_advance)]
        self.integration._shortcuts_will_change("review", shortcuts)
        self.begin()
        shortcuts[0][1]()
        self.assertFalse(self.reviewer.auto_advance_enabled)
        self.integration._clear()
        self.integration._restore_auto()
        shortcuts[0][1]()
        self.assertTrue(self.reviewer.auto_advance_enabled)

    def test_more_menu_blocks_auto_reveal_and_auto_bury_entry(self):
        self.begin()

        class Action:
            def __init__(self):
                self.enabled = True
                self.checked = True

            def shortcut(self):
                return "Shift+A"

            def setEnabled(self, enabled):
                self.enabled = enabled

            def isCheckable(self):
                return True

            def setChecked(self, checked):
                self.checked = checked

            def menu(self):
                return None

        action = Action()
        menu = SimpleNamespace(actions=lambda: [action])
        self.reviewer.auto_advance_enabled = True
        self.integration._context_menu(self.reviewer, menu)
        self.assertFalse(action.enabled)
        self.assertFalse(action.checked)
        self.assertFalse(self.reviewer.auto_advance_enabled)

    def test_response_first_captured_after_reveal_is_identified(self):
        self.begin()
        self.integration.exposed = True
        self.integration._web_message((False, None), self.current_message(), self.reviewer)
        attempt = self.events[-1]
        self.assertEqual(attempt["capture_phase"], "after_exposure")
        self.assertEqual(attempt["outcome"], "correct")

    def test_priming_is_snapshotted_before_current_answer(self):
        self.note["State"] = json.dumps({"last_exposed_day": "41",
                                         "familiarised_day": "40"})
        self.aqt.mw.col = SimpleNamespace(sched=SimpleNamespace(today=42))
        self.begin()
        self.assertFalse(self.integration.prior_exposure_today)
        self.note["State"] = json.dumps({"last_exposed_day": "42"})
        self.integration._web_message((False, None), self.current_message(), self.reviewer)
        self.assertFalse(self.events[-1]["prior_exposure_today"])
        self.begin()
        self.assertTrue(self.integration.prior_exposure_today)

    def test_native_keyboard_audio_replay_is_observed(self):
        self.begin()
        self.integration._audio_will_replay(self.reviewer.web, self.card, True)
        self.assertEqual(self.integration.replays, 1)
        self.assertEqual(self.events[-1]["source"], "native_shortcut")

    def prepare_exposure_collection(self):
        import html
        import sys
        from types import ModuleType

        class Note(dict):
            def __init__(self, identity, payload, card_id, queue=0):
                super().__init__(COMULS_ID=payload["id"],
                                 Payload=html.escape(json.dumps(payload)),
                                 State=html.escape(json.dumps({"sentinel": "preserve"})))
                self.id = identity
                self._cards = [SimpleNamespace(id=card_id, queue=queue)]

            def cards(self):
                return self._cards

        self.exercise["exposure_groups"] = ["exact-target"]
        source = Note(321, self.exercise, 123)
        sibling_payload = dict(self.exercise, id="linked")
        sibling = Note(322, sibling_payload, 124)
        sibling._cards.append(SimpleNamespace(id=125, queue=-1))
        unrelated = Note(323, dict(self.exercise, id="unrelated",
                                   exposure_groups=["other-target"]), 126)
        notes = {item["COMULS_ID"]: item for item in (source, sibling, unrelated)}
        helpers = ModuleType("comuls_review_tests.collection")
        helpers.exercise_notes = lambda col: notes
        helpers.note_payload = lambda note: json.loads(html.unescape(note["Payload"]))
        helpers.note_state = lambda note: json.loads(html.unescape(note["State"]))
        helpers._write_json = lambda note, field, value: note.__setitem__(
            field, html.escape(json.dumps(value)))
        sys.modules[helpers.__name__] = helpers
        self.note = source
        self.card.note = lambda: source
        self.bury_calls = []
        self.updated_notes = []
        collection = SimpleNamespace(
            get_note=lambda identity: source,
            sched=SimpleNamespace(
                today=42, bury_cards=lambda ids, manual: self.bury_calls.append((ids, manual))),
            add_custom_undo_entry=lambda label: 999,
            update_notes=lambda items: self.updated_notes.extend(items),
            merge_undo_entries=lambda identity: SimpleNamespace(undo=identity),
        )
        self.aqt.mw.col = collection
        return source, sibling, unrelated, collection, helpers

    def test_exposure_updates_sync_state_and_buries_only_declared_active_links(self):
        source, sibling, unrelated, collection, helpers = self.prepare_exposure_collection()
        self.begin()
        self.integration._did_show_answer(self.card)
        operation = self.FakeCollectionOp.latest
        self.assertTrue(self.integration.busy)
        result = operation.op(collection)
        self.assertEqual(result.undo, 999)
        self.assertEqual(self.bury_calls, [([124], True)])
        self.assertEqual([note.id for note in self.updated_notes], [321, 322])
        for note in (source, sibling):
            state = helpers.note_state(note)
            self.assertEqual(state["sentinel"], "preserve")
            self.assertEqual(state["last_exposed_day"], "42")
            self.assertEqual(state["last_exposed_by"], "exercise-1")
            self.assertIn("last_exposed_at", state)
        self.assertNotIn("last_exposed_at", helpers.note_state(unrelated))
        operation.success_callback(result)
        self.assertFalse(self.integration.busy)
        self.assertEqual(self.reviewer.next_calls, 0)

    def test_failed_exposure_save_keeps_grades_blocked_and_allows_safe_exit(self):
        self.prepare_exposure_collection()
        self.begin()
        self.integration._did_show_answer(self.card)
        self.FakeCollectionOp.latest.failure_callback(ValueError("save failed"))
        self.assertTrue(self.integration.busy)
        self.assertEqual(self.integration._will_answer_card((True, 3),
                                                           self.reviewer, self.card), (False, 3))
        self.assertEqual(self.events[-1]["event"], "exposure_save_failed")
        self.assertTrue(self.errors)
        self.integration._will_end()
        self.assertFalse(self.integration.busy)

    def test_capture_metadata_does_not_leak_into_next_manual_review(self):
        self.begin()
        self.integration.exposed = True
        self.integration._web_message((False, None), self.current_message(), self.reviewer)
        self.assertEqual(self.integration._attempt_metadata()["capture_phase"], "after_exposure")
        self.begin()
        metadata = self.integration._attempt_metadata()
        self.assertFalse(metadata["submitted"])
        self.assertEqual(metadata["capture_phase"], "no_submission")


if __name__ == "__main__":
    unittest.main()

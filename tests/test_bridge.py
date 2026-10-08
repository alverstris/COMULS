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
        for name in ("aqt", "aqt.operations", "aqt.reviewer", "aqt.sound",
                     "comuls_review_tests", "comuls_review_tests.bridge",
                     "comuls_review_tests.core", "comuls_review_tests.reviewer"):
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
                 "reviewer_will_end", "state_shortcuts_will_change")
        aqt_module.gui_hooks = SimpleNamespace(**{name: [] for name in names})
        aqt_module.mw = None
        operations = ModuleType("aqt.operations")
        operations.CollectionOp = FakeCollectionOp
        reviewer_module = ModuleType("aqt.reviewer")
        reviewer_module.Reviewer = NativeReviewer
        sound = ModuleType("aqt.sound")
        sound.av_player = SimpleNamespace(stop_and_clear_queue=lambda: None)
        for module in (aqt_module, operations, reviewer_module, sound):
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


if __name__ == "__main__":
    unittest.main()

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


if __name__ == "__main__":
    unittest.main()

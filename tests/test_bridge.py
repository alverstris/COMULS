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

    def test_hint_messages_match_the_portable_card_emitter(self):
        for kind, reveals, carrier in (("target", True, False), ("carrier", False, True), ("target", True, True)):
            event = bridge.validate_message(message("hint", kind=kind, reveals_target=reveals,
                                                    carrier_help=carrier), EXPECTED)
            self.assertIsNotNone(event)
            self.assertEqual(event["carrier_help"], carrier)
        self.assertIsNone(bridge.validate_message(message("hint", carrier_help="true"), EXPECTED))
        self.assertIsNone(bridge.validate_message(message("hint", kind="carrier", reveals_target=False,
                                                         carrier_help=False), EXPECTED))

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
                     "anki", "anki.sound",
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
                self.state = "question"
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
                 "reviewer_will_show_context_menu", "audio_will_replay",
                 "reviewer_will_play_question_sounds", "reviewer_will_play_answer_sounds",
                 "av_player_will_play", "av_player_did_begin_playing", "av_player_did_end_playing")
        aqt_module.gui_hooks = SimpleNamespace(**{name: [] for name in names})
        aqt_module.mw = None
        operations = ModuleType("aqt.operations")
        operations.CollectionOp = FakeCollectionOp
        reviewer_module = ModuleType("aqt.reviewer")
        reviewer_module.Reviewer = NativeReviewer
        sound = ModuleType("aqt.sound")
        sound.av_player = SimpleNamespace(stop_and_clear_queue=lambda: None,
                                          play_tags=lambda tags: None)
        native_sound = ModuleType("anki.sound")
        native_sound.SoundOrVideoTag = lambda filename: SimpleNamespace(filename=filename)
        if "anki" not in sys.modules:
            native_package = ModuleType("anki")
            native_package.__path__ = []
            sys.modules["anki"] = native_package
        sys.modules["anki.sound"] = native_sound
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
        import sys
        from types import ModuleType
        self.events = []
        self.errors = []
        self.played_audio = []
        self.module.av_player.play_tags = self.played_audio.extend
        self.controller = SimpleNamespace(on_event=self.events.append,
                                          content_error=self.errors.append)
        self.reviewer = self.NativeReviewer()
        self.aqt.mw = SimpleNamespace(state="review", reviewer=self.reviewer,
                                      col=SimpleNamespace(sched=SimpleNamespace(today=42)))
        # Every test starts with its own adapter fixture. Do not let an exposure
        # test's richer stub leak into later reviewer tests through sys.modules.
        helpers = ModuleType("comuls_review_tests.collection")
        helpers.evidence_state = lambda col, note: json.loads(html.unescape(note.get("State", "{}")))
        sys.modules[helpers.__name__] = helpers
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

    def current_event(self, event, **details):
        return bridge.PREFIX + json.dumps(dict(self.integration.expected, event=event, **details))

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
                                                           "comuls:{", None), (True, None))
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

    def test_invalid_managed_card_keeps_auto_off_and_cannot_receive_a_grade(self):
        self.note["Payload"] = "{invalid"
        self.reviewer.auto_advance_enabled = True
        page = self.begin()
        self.assertIn("COMULS card unavailable", page)
        self.assertIn("Skip without grading", page)
        self.assertFalse(self.reviewer.auto_advance_enabled)
        self.assertTrue(self.integration._live())
        for grade in (1, 2, 3, 4):
            self.assertEqual(self.integration._will_answer_card((True, grade), self.reviewer, self.card), (False, grade))
        self.integration._did_show_question(self.card)
        self.integration._did_show_answer(self.card)
        self.integration._web_message((False, None), self.current_message(), self.reviewer)
        self.assertFalse(self.integration.latch.submitted)
        self.assertFalse(any(event["event"] in ("question", "answer_exposure", "attempt") for event in self.events))
        self.assertIn("unavailable", self.integration._card_will_show("back", self.card, "reviewAnswer"))
        request = dict(self.integration.expected, event="skip", reason="content_unavailable")
        self.integration._web_message((False, None), bridge.PREFIX + json.dumps(request), self.reviewer)
        self.assertIsNotNone(self.FakeCollectionOp.latest)
        self.assertEqual(self.reviewer.next_calls, 0)
        self.FakeCollectionOp.latest.success_callback(None)
        self.assertEqual(self.reviewer.next_calls, 1)

    def test_empty_managed_identity_is_unavailable_but_foreign_cards_remain_native(self):
        self.note["COMULS_ID"] = ""
        self.assertIn("unavailable", self.begin())
        self.assertEqual(self.integration._will_answer_card((True, 1), self.reviewer, self.card), (False, 1))
        del self.note["COMULS_ID"]
        self.assertIn("<main>template</main>", self.begin())
        self.assertIsNone(self.integration.expected)
        self.assertEqual(self.integration._will_answer_card((True, 3), self.reviewer, self.card), (True, 3))

    def test_missing_or_changed_recording_blocks_learning_grade(self):
        import html
        import hashlib
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "primary.wav"
            self.exercise["audio_file"] = path.name
            self.exercise["audio_sha256"] = hashlib.sha256(b"known-bytes").hexdigest()
            self.note["Payload"] = html.escape(json.dumps(self.exercise))
            self.aqt.mw.col = SimpleNamespace(media=SimpleNamespace(dir=lambda: directory))
            self.assertIn("recording is unavailable", self.begin())
            self.assertEqual(self.integration._will_answer_card((True, 1), self.reviewer, self.card), (False, 1))
            path.write_bytes(b"damaged")
            self.assertIn("recording is damaged", self.begin())
            path.write_bytes(b"known-bytes")
            self.assertNotIn("unavailable</h2>", self.begin())
            self.assertEqual(self.integration._will_answer_card((True, 3), self.reviewer, self.card), (True, 3))
            path.unlink()
            self.assertEqual(self.integration._will_answer_card((True, 3), self.reviewer, self.card), (False, 3))

    def test_missing_contrast_recording_blocks_before_question(self):
        import html
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            self.exercise.update(type="sound_discrimination", audio_text="rue", answer="rue",
                choices=[{"id": "rue", "text": "rue", "correct": True, "audio_file": "rue.wav"},
                         {"id": "roue", "text": "roue", "correct": False, "audio_file": "roue.wav"}])
            self.note["Payload"] = html.escape(json.dumps(self.exercise))
            self.aqt.mw.col = SimpleNamespace(media=SimpleNamespace(dir=lambda: directory))
            (Path(directory) / "rue.wav").write_bytes(b"present")
            self.assertIn("recording is unavailable", self.begin())
            self.assertFalse(self.integration.exposed)
            self.assertEqual(self.integration._will_answer_card((True, 3), self.reviewer, self.card), (False, 3))

    def test_unsafe_media_path_is_not_read(self):
        import html
        self.exercise["audio_file"] = "../outside.wav"
        self.note["Payload"] = html.escape(json.dumps(self.exercise))
        self.assertIn("invalid recording reference", self.begin())
        self.assertEqual(self.integration._will_answer_card((True, 3), self.reviewer, self.card), (False, 3))

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
                                         "familiarised_day": "40", "last_exposed_at": 1700000000.25})
        self.aqt.mw.col = SimpleNamespace(sched=SimpleNamespace(today=42))
        self.begin()
        self.assertFalse(self.integration.prior_exposure_today)
        self.assertEqual(self.integration.prior_exposed_at, 1700000000.25)
        self.note["State"] = json.dumps({"last_exposed_day": "42", "last_exposed_at": 1700086400.5})
        self.integration._web_message((False, None), self.current_message(), self.reviewer)
        self.assertFalse(self.events[-1]["prior_exposure_today"])
        self.assertEqual(self.events[-1]["prior_exposed_at"], 1700000000.25)
        self.begin()
        self.assertTrue(self.integration.prior_exposure_today)
        self.assertEqual(self.integration.prior_exposed_at, 1700086400.5)

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
        helpers.evidence_state = lambda col, note: helpers.note_state(note)
        self.factual_exposures = []
        helpers.record_reference_exposure = lambda col, identity, when: self.factual_exposures.append((identity, when))
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
        self.assertEqual(len(self.factual_exposures), 1)
        self.assertEqual(self.factual_exposures[0][0], "exercise-1")
        self.assertGreater(self.factual_exposures[0][1], 0)
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

    def test_comparison_audio_resolves_only_current_choices_after_reveal(self):
        self.begin()
        self.integration.exercise = dict(self.exercise, choices=[
            {"id": "choice-safe", "audio_file": "bundled-contrast.wav"}])
        event = self.current_event("play_comparison", choice_id="choice-safe")
        self.integration._web_message((False, None), event, self.reviewer)
        self.assertEqual(self.played_audio, [])
        self.reviewer.state = "answer"
        self.integration._web_message((False, None),
            self.current_event("play_comparison", choice_id="../../unknown.wav"), self.reviewer)
        self.assertEqual(self.played_audio, [])
        self.integration._web_message((False, None), event, self.reviewer)
        self.assertEqual([tag.filename for tag in self.played_audio], ["bundled-contrast.wav"])
        self.assertEqual(self.events[-1]["source"], "comparison")
        self.assertEqual(self.events[-1]["side"], "back")
        self.assertEqual(self.integration.replays, 0)

    def test_native_question_replays_survive_later_zero_replay_submission(self):
        self.begin()
        self.integration._audio_will_replay(self.reviewer.web, self.card, True)
        self.integration._audio_will_replay(self.reviewer.web, self.card, True)
        self.integration._web_message((False, None), self.current_message(replays=0), self.reviewer)
        self.assertEqual(self.events[-1]["replays"], 2)
        self.integration._did_answer_card(self.reviewer, self.card, 3)
        self.assertEqual(self.events[-1]["replays"], 2)
        self.begin()
        self.assertEqual(self.integration.replays, 0)

    def test_install_and_close_own_new_audio_hooks_without_leaking_registrations(self):
        self.integration.install()
        for name in ("reviewer_will_play_question_sounds", "reviewer_will_play_answer_sounds"):
            self.assertEqual(len(getattr(self.aqt.gui_hooks, name)), 1)
        self.integration.close()
        for name in ("reviewer_will_play_question_sounds", "reviewer_will_play_answer_sounds"):
            self.assertEqual(getattr(self.aqt.gui_hooks, name), [])

    def test_autoplay_filter_detaches_cached_tags_so_native_replay_remains_available(self):
        self.controller.state = lambda: {"audio_autoplay": False}
        question_tag = SimpleNamespace(filename="primary-question.wav")
        answer_tag = SimpleNamespace(filename="primary-answer.wav")
        cached = SimpleNamespace(question_av_tags=[question_tag], answer_av_tags=[answer_tag])
        self.card.render_output = lambda: cached
        question_queue, answer_queue = cached.question_av_tags, cached.answer_av_tags
        self.integration._question_sounds(self.card, question_queue)
        self.integration._answer_sounds(self.card, answer_queue)
        self.assertEqual(question_queue, [])
        self.assertEqual(answer_queue, [])
        self.assertEqual(cached.question_av_tags, [question_tag])
        self.assertEqual(cached.answer_av_tags, [answer_tag])

    def test_foreign_card_audio_queues_are_untouched(self):
        card = SimpleNamespace(note=lambda: {"Front": "not COMULS"})
        sounds = [SimpleNamespace(filename="other-course.wav")]
        self.integration._question_sounds(card, sounds)
        self.integration._answer_sounds(card, sounds)
        self.assertEqual([tag.filename for tag in sounds], ["other-course.wav"])

    def test_audio_completion_requires_current_nonce_player_and_elapsed_playback(self):
        from unittest.mock import patch
        self.begin()
        scripts = []
        self.reviewer.web = SimpleNamespace(eval=scripts.append)
        player = object()
        valid = {"card_id": 123, "nonce": self.integration.expected["nonce"],
                 "filename": "primary.wav", "duration": 10, "started": 90, "player_id": id(player)}
        with patch.object(self.module.time, "monotonic", return_value=100):
            for invalid in (dict(valid, nonce="previous-render"), dict(valid, card_id=124),
                            dict(valid, started=99), dict(valid, player_id=id(object())),
                            dict(valid, started=None)):
                self.integration._audio_playback = invalid
                self.integration._playback_ended(player)
                self.assertEqual(scripts, [])
            self.reviewer.state = "answer"
            self.integration._audio_playback = dict(valid)
            self.integration._playback_ended(player)
            self.assertEqual(scripts, [])
            self.reviewer.state = "question"
            self.integration._audio_playback = dict(valid)
            self.integration._playback_ended(player)
            self.assertEqual(len(scripts), 1)
            self.assertIn(self.integration.expected["nonce"], scripts[0])
            self.integration._playback_ended(player)
            self.assertEqual(len(scripts), 1)


if __name__ == "__main__":
    unittest.main()

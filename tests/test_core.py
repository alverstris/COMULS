"""Consequential curriculum/assessment tests; runnable without Anki or Qt."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

# Loading core directly avoids invoking the live Anki add-on entry point.
CORE_PATH = Path(__file__).resolve().parents[1] / "addon" / "core.py"
SPEC = importlib.util.spec_from_file_location("comuls_core_for_tests", CORE_PATH)
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


def exercise(kind="french_form_recall", level="B1", entries=None):
    item = {
        "id": "exercise-1", "type": kind, "level": level,
        "entry_levels": entries or ["B1", "B2", "C1"],
        "prompt": "Write the French form.", "answer": "Écoute !",
        "accepted": [], "unit_id": "sense:listen",
        "prerequisites": [], "exposure_groups": ["context:listen"],
        "qa": {"ready": True, "level_status": "provisional"},
        "provenance": {"kind": "original", "author": "COMULS"},
        "audio_text": "Écoute !",
    }
    if kind in core.CHOICE_TYPES:
        item["choices"] = [
            {"id": "listen", "text": "Listen", "correct": True},
            {"id": "write", "text": "Write", "correct": False},
        ]
    return item


def pack(*items):
    return {"schema_version": 1, "pack_id": "test-pack", "version": "1.0.0",
            "exercises": list(items or (exercise(),))}


def support(identity="carrier:listen", requires=None, level="A2", scope="fixed_carrier_use"):
    return {"id": identity, "kind": "construction", "label": "A request",
            "text": "s'il vous plaît", "english": "please", "level": level,
            "requires": requires or [], "minimum_state": "understood",
            "modality": "reading", "scope": scope}


def admission(item, stage="B1", familiarised=True, understood=None, budget=None):
    return core.admission_decision(
        item, stage, familiarised, understood or set(), set(core.EXERCISE_TYPES),
        budget or {},
    )


class AdmissionTests(unittest.TestCase):
    def test_synthesis_requires_every_complexity_dimension_below_stage(self):
        for kind in core.SYNTHESIS_TYPES:
            with self.subTest(kind=kind):
                item = exercise(kind, "A2+")
                self.assertTrue(admission(item)["allowed"])
                for field in ("level", "target_level", "carrier_level", "construction_level"):
                    changed = dict(item, **{field: "B1"})
                    result = admission(changed)
                    self.assertFalse(result["allowed"])
                    self.assertIn(field + "_above_ceiling", result["reasons"])

    def test_concurrent_listening_windows_are_different(self):
        full = exercise("sentence_transcription", "B1+")
        self.assertTrue(admission(full)["allowed"])
        full["level"] = "B2"
        self.assertIn("level_above_ceiling", admission(full)["reasons"])
        choice = exercise("audio_meaning_choice", "B2")
        self.assertTrue(admission(choice)["allowed"])
        choice["level"] = "B2+"
        self.assertFalse(admission(choice)["allowed"])
        word = exercise("connected_word_recognition", "B1+")
        self.assertFalse(admission(word)["allowed"])

    def test_c1_listening_can_use_provisionally_authored_c2(self):
        item = exercise("audio_transcript_choice", "C2", ["C1"])
        self.assertTrue(admission(item, "C1")["allowed"])
        item["type"] = "sentence_transcription"
        self.assertFalse(admission(item, "C1")["allowed"])

    def test_familiarity_is_required_even_for_same_or_lower_level(self):
        for level in ("A2", "B1", "B1+"):
            item = exercise("sentence_transcription", level)
            self.assertIn("familiarisation_required",
                          admission(item, familiarised=False)["reasons"])

    def test_carrier_prerequisites_are_exact_senses(self):
        item = exercise()
        item["prerequisites"] = ["prendre:idiom", "support:since"]
        result = admission(item, understood={"prendre:take", "support:since"})
        self.assertEqual(result["missing_prerequisites"], ["prendre:idiom"])
        self.assertIn("prerequisites_missing", result["reasons"])

    def test_readiness_availability_and_enabled_type_are_independent(self):
        item = exercise(entries=["B2"])
        item["qa"]["ready"] = False
        result = core.admission_decision(item, "B1", True, set(), set(), {})
        for reason in ("entry_level_unavailable", "content_not_ready", "exercise_disabled"):
            self.assertIn(reason, result["reasons"])

    def test_retired_and_blocked_catalog_items_cannot_be_admitted(self):
        for changes in ({"retired": True}, {"content_status": "retired"}, {"content_status": "content_blocked"}):
            self.assertIn("content_blocked", admission(dict(exercise(), **changes), budget={"override": True})["reasons"])

    def test_pure_level_gate_ignores_budget_and_familiarity(self):
        item = exercise("sentence_transcription", "B1+")
        item["qa"]["ready"] = False
        item["prerequisites"] = ["unknown-carrier"]
        self.assertTrue(core.level_eligible(item, "B1"))
        self.assertFalse(admission(item, familiarised=False)["allowed"])
        item["carrier_level"] = "B2"
        self.assertFalse(core.level_eligible(item, "B1"))
        self.assertTrue(core.level_eligible(item, "B2"))

    def test_caps_count_units_separately_from_cards(self):
        item = exercise()
        self.assertIn("daily_unit_limit", admission(item, budget={"new_units": 6})["reasons"])
        item["unit_already_introduced"] = True
        self.assertTrue(admission(item, budget={"new_units": 6})["allowed"])
        self.assertIn("daily_card_limit",
                      admission(item, budget={"admitted_cards": 8})["reasons"])

    def test_configured_zero_and_reduced_caps_are_enforced(self):
        item = exercise()
        self.assertIn("daily_card_limit", admission(item, budget={"max_new_cards": 0})["reasons"])
        self.assertIn("daily_unit_limit", admission(item, budget={"max_new_units": 0})["reasons"])
        self.assertIn("daily_card_limit", admission(item, budget={"max_new_cards": 2, "admitted_cards": 2})["reasons"])
        self.assertIn("daily_unit_limit", admission(item, budget={"max_new_units": 2, "new_units": 2})["reasons"])
        self.assertTrue(admission(item, budget={"max_new_cards": 10, "admitted_cards": 8,
                                                "max_new_units": 9, "new_units": 7})["allowed"])
        item["unit_already_introduced"] = True
        self.assertTrue(admission(item, budget={"max_new_units": 0, "new_units": 2})["allowed"])

    def test_preview_cap_is_separate_and_cannot_be_overridden(self):
        item = exercise("sentence_transcription", "B1+")
        self.assertIn("daily_preview_limit", admission(item, budget={"preview_units": 1})["reasons"])
        self.assertIn("daily_preview_limit", admission(item, budget={"max_preview_units": 0, "override": True})["reasons"])
        item["unit_already_introduced"] = True
        self.assertTrue(admission(item, budget={"max_preview_units": 0})["allowed"])

    def test_support_acquisition_cannot_hide_extra_units_in_one_card(self):
        item = exercise()
        item["new_unit_cost"] = 3
        self.assertIn("daily_unit_limit", admission(item, budget={"max_new_units": 6, "new_units": 4})["reasons"])
        item["new_unit_cost"] = 0
        self.assertIn("daily_unit_limit", admission(item, budget={"max_new_units": 0})["reasons"])

    def test_invalid_count_settings_fail_closed(self):
        for field in ("new_units", "admitted_cards", "preview_units", "max_new_units", "max_new_cards", "max_preview_units"):
            for value in (-1, 0.5, True, "2", None):
                self.assertIn("invalid_budget", admission(exercise(), budget={field: value})["reasons"])

    def test_transitive_prerequisite_must_be_understood(self):
        item = exercise()
        item["support_units"] = [support("outer", ["inner"]), support("inner")]
        item["prerequisites"] = ["outer"]
        result = admission(item, understood={"outer"})
        self.assertEqual(result["missing_prerequisites"], ["inner"])
        self.assertTrue(admission(item, understood={"outer", "inner"})["allowed"])

    def test_malformed_live_admission_fails_without_raising(self):
        for field in ("type", "qa", "entry_levels", "prerequisites", "support_units"):
            item = exercise()
            item[field] = None
            self.assertFalse(admission(item)["allowed"])
        item = exercise()
        item["type"] = []
        self.assertFalse(admission(item)["allowed"])
        self.assertFalse(core.level_eligible(dict(item, entry_levels=None), "B1"))

    def test_override_does_not_bypass_learning_or_daily_caps(self):
        item = exercise()
        budget = {"pause_new": True, "remaining_seconds": 80, "due_seconds": 160}
        result = admission(item, budget=budget)
        self.assertIn("new_admission_paused", result["reasons"])
        self.assertIn("review_backlog", result["reasons"])
        budget["override"] = True
        self.assertTrue(admission(item, budget=budget)["allowed"])
        budget["admitted_cards"] = 8
        result = admission(item, familiarised=False, budget=budget)
        self.assertIn("daily_card_limit", result["reasons"])
        self.assertIn("familiarisation_required", result["reasons"])

    def test_time_budget_includes_estimated_next_exercise(self):
        item = exercise()
        item["estimated_seconds"] = 30
        self.assertFalse(admission(item, budget={"remaining_seconds": 89})["allowed"])
        self.assertTrue(admission(item, budget={"remaining_seconds": 90})["allowed"])
        self.assertFalse(admission(item, budget={"remaining_seconds": 0, "override": True})["allowed"])
        self.assertIn("invalid_budget", admission(item, budget={"new_units": float("nan")})["reasons"])

    def test_forecast_reserves_preparation_retrieval_relearning_and_support(self):
        item = dict(exercise(), estimated_seconds=20, new_unit_cost=3)
        forecast = core.admission_forecast(item, {})
        self.assertEqual(forecast, {"first_review_seconds": 20, "relearning_allowance_seconds": 20,
            "preparation_seconds": 20, "support_seconds": 40, "required_seconds": 100})
        self.assertFalse(admission(item, budget={"remaining_seconds": 99})["allowed"])
        self.assertIn("review_backlog", admission(item, budget={"remaining_seconds": 110, "due_seconds": 20})["reasons"])

    def test_completed_preparation_is_not_double_counted_in_remaining_work(self):
        item = dict(exercise(), estimated_seconds=20, new_unit_cost=3, preparation_complete=True)
        result = admission(item, budget={"remaining_seconds": 40})
        self.assertTrue(result["allowed"])
        self.assertEqual(result["forecast"]["required_seconds"], 40)
        self.assertEqual(result["forecast"]["support_seconds"], 0)
        self.assertIn("daily_unit_limit", admission(item, budget={"new_units": 4})["reasons"])

    def test_observed_per_type_time_replaces_prior_only_for_forecasting(self):
        item = dict(exercise(), estimated_seconds=20)
        self.assertEqual(core.admission_forecast(item, {"timings": {item["type"]: 12}})["required_seconds"], 39)
        self.assertEqual(item["estimated_seconds"], 20)
        for value in (0, float("nan"), "20"):
            self.assertIn("invalid_budget", admission(item, budget={"timings": {item["type"]: value}})["reasons"])


class EvaluationTests(unittest.TestCase):
    def test_typography_and_unicode_canonical_equivalence(self):
        self.assertEqual(core.normalize_answer("  L’ e\u0301cole\u00a0! "), "l'école")
        self.assertEqual(core.normalize_answer("Pense\u2011t\u2011il ?"), "pense-t-il")
        self.assertEqual(core.normalize_answer("Écoute !"), "écoute")

    def test_accents_and_meaningful_punctuation_remain_distinct(self):
        self.assertNotEqual(core.normalize_answer("ou"), core.normalize_answer("où"))
        self.assertNotEqual(core.normalize_answer("a"), core.normalize_answer("à"))
        self.assertNotEqual(core.normalize_answer("il est parti"), core.normalize_answer("il n'est pas parti"))
        self.assertNotEqual(core.normalize_answer("c'est"), core.normalize_answer("cest"))
        self.assertNotEqual(core.normalize_answer("écoute!", "punctuation"),
                            core.normalize_answer("écoute", "punctuation"))

    def test_exact_alternatives_only(self):
        item = exercise()
        self.assertEqual(core.evaluate_answer(item, "e\u0301coute.")["status"], "correct")
        self.assertEqual(core.evaluate_answer(item, "ecoute")["status"], "incorrect")
        item["accepted"] = ["Écoutez !"]
        self.assertEqual(core.evaluate_answer(item, "écoutez")["status"], "correct")

    def test_reveal_without_captured_attempt_never_invents_failure(self):
        for response in (None, "", "   ", {}):
            self.assertEqual(core.evaluate_answer(exercise(), response)["status"], "self_compare")

    def test_semantic_recall_and_unknown_transformations_remain_honest(self):
        item = exercise("meaning_recall")
        self.assertEqual(core.evaluate_answer(item, "A reasonable paraphrase")["status"], "self_compare")
        item = exercise("sentence_transformation", "A2+")
        self.assertEqual(core.evaluate_answer(item, "Écoute")["status"], "correct")
        self.assertEqual(core.evaluate_answer(item, "An unlisted construction")["status"], "self_compare")

    def test_choice_is_graded_by_stable_id_not_position_or_label(self):
        item = exercise("audio_meaning_choice")
        item["choices"].reverse()
        self.assertEqual(core.evaluate_answer(item, "listen")["status"], "correct")
        self.assertEqual(core.evaluate_answer(item, {"choice_id": "write"})["status"], "incorrect")
        self.assertEqual(core.evaluate_answer(item, "Listen")["status"], "incorrect")

    def test_connected_word_recognition_uses_stable_choice_ids(self):
        item = exercise("connected_word_recognition")
        item["choices"].reverse()
        self.assertEqual(core.validate_pack(pack(item)), [])
        self.assertEqual(core.evaluate_answer(item, "listen")["status"], "correct")
        self.assertEqual(core.evaluate_answer(item, "write")["status"], "incorrect")
        self.assertEqual(core.evaluate_answer(item, "Listen")["status"], "incorrect")

    def test_repeated_equivalent_tiles_can_exchange_positions(self):
        item = exercise("sentence_reconstruction", "A2+")
        item["answer"] = "Il dit il"
        item["tokens"] = [
            {"id": "a", "text": "Il"}, {"id": "b", "text": "dit"},
            {"id": "c", "text": "il"},
        ]
        self.assertEqual(core.evaluate_answer(item, ["c", "b", "a"])["status"], "correct")
        self.assertEqual(core.evaluate_answer(item, ["a", "c", "b"])["status"], "incorrect")
        # Malformed/corrupted UI state is not evidence of student failure.
        self.assertEqual(core.evaluate_answer(item, ["a", "b", "a"])["status"], "self_compare")


class PackTests(unittest.TestCase):
    def test_valid_pack_and_utf8_bom(self):
        item = pack()
        self.assertEqual(core.validate_pack(item), [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pack.json"
            path.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8-sig")
            self.assertEqual(core.load_pack(path)["pack_id"], "test-pack")

    def test_bad_identity_and_unready_content_are_rejected(self):
        item = exercise()
        bad = copy.deepcopy(item)
        bad["qa"]["ready"] = False
        errors = core.validate_pack(pack(item, bad))
        self.assertTrue(any("duplicates" in error for error in errors))
        self.assertTrue(any("qa.ready" in error for error in errors))

    def test_exact_support_closure_is_portable_and_requires_english_bridge(self):
        item = exercise()
        item["support_units"] = [support()]
        item["prerequisites"] = ["carrier:listen"]
        self.assertEqual(core.validate_pack(pack(item)), [])
        item["support_units"][0]["english"] = ""
        self.assertTrue(any("english" in error for error in core.validate_pack(pack(item))))

    def test_missing_cyclic_and_target_dependencies_are_rejected(self):
        item = exercise()
        item["prerequisites"] = ["missing"]
        self.assertTrue(any("unresolved" in error for error in core.validate_pack(pack(item))))
        item["support_units"] = [support("a", ["b"]), support("b", ["a"])]
        item["prerequisites"] = ["a"]
        self.assertTrue(any("cycle" in error for error in core.validate_pack(pack(item))))
        item["support_units"] = [support(item["unit_id"])]
        item["prerequisites"] = [item["unit_id"]]
        self.assertTrue(any("trained target" in error for error in core.validate_pack(pack(item))))

    def test_support_levels_do_not_inherit_listening_preview_allowance(self):
        item = exercise("audio_meaning_choice", "B2", ["B1"])
        item["support_units"] = [support(level="B1+")]
        item["prerequisites"] = ["carrier:listen"]
        self.assertTrue(any("support ceiling" in error for error in core.validate_pack(pack(item))))
        item["support_units"] = [support(level="B1", scope="definition_support")]
        self.assertTrue(any("support ceiling" in error for error in core.validate_pack(pack(item))))
        item["support_units"][0]["level"] = "A2"
        self.assertEqual(core.validate_pack(pack(item)), [])

    def test_identical_choice_labels_do_not_form_an_assessable_question(self):
        item = exercise("sound_discrimination")
        item["choices"][1]["text"] = "LISTEN."
        self.assertTrue(any("indistinguishable" in error for error in core.validate_pack(pack(item))))

    def test_advertised_entry_levels_must_respect_all_task_dimensions(self):
        item = exercise("vocabulary_cloze", "A2+")
        item["carrier_level"] = "B1"
        self.assertTrue(any("exceeds B1" in error for error in core.validate_pack(pack(item))))

    def test_ambiguous_choices_and_missing_audio_are_rejected(self):
        item = exercise("sound_discrimination")
        item["choices"][1]["correct"] = True
        item["audio_text"] = ""
        errors = core.validate_pack(pack(item))
        self.assertTrue(any("exactly one correct" in error for error in errors))
        self.assertTrue(any("requires audio" in error for error in errors))

    def test_malformed_untrusted_json_returns_errors(self):
        for value in (None, [], {}, {"schema_version": 1, "exercises": [None]}):
            self.assertTrue(core.validate_pack(value))
        item = exercise()
        item["type"] = []
        self.assertTrue(core.validate_pack(pack(item)))

    def test_load_rejects_bad_pack_with_useful_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(pack(exercise("vocabulary_cloze", "B1"))), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exceeds B1"):
                core.load_pack(path)

    def test_hash_tracks_retrieval_changes_but_not_editorial_changes(self):
        item = exercise("audio_meaning_choice")
        before = core.semantic_hash(item)
        item["choices"].reverse()
        item["explanation"] = "Clearer feedback"
        item["qa"]["level_status"] = "reviewed"
        item["provenance"]["author"] = "Updated metadata"
        self.assertEqual(core.semantic_hash(item), before)
        item["audio_text"] = "A different sentence."
        self.assertNotEqual(core.semantic_hash(item), before)

    def test_hash_tracks_new_accepted_answer_and_target(self):
        item = exercise()
        before = core.semantic_hash(item)
        item["accepted"] = ["Écoutez"]
        self.assertNotEqual(core.semantic_hash(item), before)
        item = exercise()
        item["unit_id"] = "a-different-sense"
        self.assertNotEqual(core.semantic_hash(item), before)

    def test_hash_tracks_contrast_audio_even_when_choice_wording_is_unchanged(self):
        for field in ("audio_file", "audio_sha256", "audio_text"):
            item = exercise("sound_discrimination")
            before = core.semantic_hash(item)
            item["choices"][1][field] = "changed-alternative-recording"
            self.assertNotEqual(core.semantic_hash(item), before)


if __name__ == "__main__":
    unittest.main()

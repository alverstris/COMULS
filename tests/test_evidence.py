"""Evidence claims are bounded by native history, exact objectives and assistance."""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

PACKAGE = "_comuls_evidence_test"
if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(Path(__file__).resolve().parents[1] / "addon")]
    sys.modules[PACKAGE] = package
evidence = importlib.import_module(PACKAGE + ".evidence")

BASE = 1_700_000_000
EXERCISE = {"id": "exact-listening", "unit_id": "sense-1", "type": "partial_dictation",
            "sense_id": "sense-1", "form_id": "form-1", "evidence_facets": ["transcription"]}


def native(seconds, grade=3, kind=1, offset=0):
    return {"id": int(seconds * 1000) + offset, "button_chosen": grade, "review_kind": kind}


def meta(prior, day, **overrides):
    return dict({"assistance_known": True, "capture_phase": "question", "target_hint": False,
                 "carrier_help": False, "replays": 0, "prior_exposure_today": False,
                 "prior_exposed_at": prior, "study_day": day, "outcome": "correct"}, **overrides)


def summary(logs, records=None, **state):
    return evidence.summarize_exercise(EXERCISE, dict(state, review_evidence=records or {}), logs, BASE + 10 * 86400)


def test_no_grade_is_fabricated_from_familiarisation_or_declaration():
    result = summary([], familiarised_day="1", declared_understood=True)
    assert result["understood"] and result["familiarised"]
    assert result["total_reviews"] == result["independent_successes"] == 0
    assert not result["stable"]


def test_native_mobile_grades_have_recall_evidence_but_unknown_independence():
    result = summary([native(BASE), native(BASE + 2 * 86400)])
    assert result["understood"]
    assert result["unknown_assistance_reviews"] == 2
    assert not result["stable"]


def test_two_delayed_unaided_dates_establish_only_exact_objective():
    logs = [native(BASE + 2 * 86400), native(BASE + 4 * 86400)]
    records = {str(logs[0]["id"]): meta(BASE, "2"),
               str(logs[1]["id"]): meta(BASE + 2 * 86400, "4")}
    result = summary(logs, records)
    assert result["stable"]
    assert result["independent_dates"] == 2
    assert result["facets"] == ["transcription"]
    assert result["objective"] == "partial_dictation"
    assert result["form_id"] == "form-1"


def test_native_undo_removes_credit_and_redo_can_restore_it():
    logs = [native(BASE + 2 * 86400), native(BASE + 4 * 86400)]
    records = {str(logs[0]["id"]): meta(BASE, "2"), str(logs[1]["id"]): meta(BASE + 2 * 86400, "4")}
    assert summary(logs, records)["stable"]
    assert not summary(logs[:1], records)["stable"]
    assert summary(logs, records)["stable"]


def test_repeated_grade_same_second_does_not_inherit_undone_metadata():
    old = native(BASE + 2 * 86400, offset=5)
    new = native(BASE + 2 * 86400, offset=8)
    result = summary([new], {str(old["id"]): meta(BASE, "2")})
    assert result["independent_successes"] == 0


def test_native_display_timestamps_use_exact_adapter_rows_when_available():
    exact = native(BASE + 2 * 86400, offset=999)
    rounded = {"time": BASE + 2 * 86400, "button_chosen": 3, "review_kind": 1}
    result = summary([rounded], {str(exact["id"]): meta(BASE, "2")}, native_reviews=[exact])
    assert result["independent_successes"] == 1
    assert summary([rounded], {str(exact["id"]): meta(BASE, "2")}, native_reviews=[])["total_reviews"] == 0


def test_failure_after_stability_requires_two_new_independent_dates():
    logs = [native(BASE + i * 86400, grade=1 if i == 4 else 3) for i in (2, 3, 4, 6, 8)]
    records = {str(log["id"]): meta(log["id"] / 1000 - 2 * 86400, str(i)) for i, log in enumerate(logs)}
    assert summary(logs[:2], records)["stable"]
    assert summary(logs[:3], records)["repair_needed"]
    assert not summary(logs[:4], records)["stable"]
    assert summary(logs, records)["stable"]


def test_same_day_two_reviews_and_recent_exposure_never_establish_stability():
    logs = [native(BASE + 2 * 86400), native(BASE + 2 * 86400 + 3600)]
    records = {str(log["id"]): meta(BASE, "2") for log in logs}
    assert not summary(logs, records)["stable"]
    records[str(logs[-1]["id"])] = meta(BASE + 2 * 86400, "3")
    assert summary(logs, records)["independent_successes"] == 1


def test_assistance_and_priming_are_not_independent_and_hints_are_not_understood():
    for overrides in ({"target_hint": True}, {"carrier_help": True}, {"replays": 1},
                      {"capture_phase": "after_exposure"}, {"prior_exposure_today": True},
                      {"prior_exposed_at": None}, {"assistance_known": False}):
        log = native(BASE + 2 * 86400)
        result = summary([log], {str(log["id"]): meta(BASE, "2", **overrides)})
        assert result["independent_successes"] == 0
        if overrides.get("target_hint") or overrides.get("capture_phase") == "after_exposure":
            assert not result["understood"]


def test_native_good_over_incorrect_answer_is_not_claimed_as_success():
    log = native(BASE + 2 * 86400)
    result = summary([log], {str(log["id"]): meta(BASE, "2", outcome="incorrect")})
    assert result["repair_needed"] and not result["understood"]


def test_manual_self_comparison_can_supply_unaided_learner_reported_recall():
    log = native(BASE + 2 * 86400)
    result = summary([log], {str(log["id"]): meta(BASE, "2", outcome="self_compare", capture_phase="no_submission")})
    assert result["independent_successes"] == 1


def test_nonreview_administrative_history_and_future_entries_are_ignored():
    logs = [native(BASE, grade=0), native(BASE, kind=4), native(BASE + 12 * 86400)]
    assert summary(logs)["total_reviews"] == 0


def test_iso_timestamps_require_explicit_timezone_and_keep_millisecond_precision():
    assert evidence.timestamp("2023-11-14T22:13:20Z") == BASE
    assert evidence.timestamp("2023-11-14T22:13:20") is None
    assert evidence.timestamp(BASE * 1000 + 999) == BASE + .999
    assert evidence.timestamp(float("nan")) is None

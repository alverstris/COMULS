"""Cohort separation and non-authoritative diagnostic boundary tests."""
import importlib
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "_comuls_course_test"
package = types.ModuleType(NAME)
package.__path__ = [str(ROOT / "addon")]
sys.modules[NAME] = package
course = importlib.import_module(NAME + ".course")
placement = importlib.import_module(NAME + ".placement")


def test_course_default_does_not_offer_c1(tmp_path):
    assert course.COHORTS == ("B1", "B2")
    (tmp_path / "course_profile.json").write_text('{"cohort":"B2"}')
    assert course.suggested_cohort(tmp_path) == "B2"
    (tmp_path / "course_profile.json").write_text('{"cohort":"C1"}')
    assert course.suggested_cohort(tmp_path) == "B1"


def test_default_routes_are_separate_and_repair_is_explicit():
    catalog = [
        {"id": "b1", "origin_entry_level": "B1"},
        {"id": "b2", "cohort": "B2"},
    ]
    assert [e["id"] for e in course.route_candidates(catalog, "B1")] == ["b1"]
    assert [e["id"] for e in course.route_candidates(catalog, "B2")] == ["b2"]
    assert [e["id"] for e in course.route_candidates(catalog, "B2", repair=True)] == ["b1", "b2"]


def test_diagnostic_stops_at_available_routes_without_promoting_collection():
    assert placement.recommend(3, 4, "B1") == {"action": "higher", "stage": "B2"}
    assert placement.recommend(1, 4, "B2") == {"action": "lower", "stage": "B1"}
    assert placement.recommend(2, 4, "B1") == {"action": "more", "stage": "B1"}
    assert placement.recommend(1, 2, "B1")["action"] == "insufficient"

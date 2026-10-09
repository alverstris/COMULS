"""Load bounded, declarative course packs and preserve separate student routes."""
from __future__ import annotations
import json
from pathlib import Path
from .core import load_pack, validate_pack

COHORTS = ("B1", "B2")

def load_course(root: Path, override: Path | None = None):
    if override is not None and override.is_file():
        return load_pack(override)
    paths = [root / "data" / ("imperial_" + stage.lower() + ".json") for stage in COHORTS]
    present = [path.is_file() for path in paths]
    if any(present) and not all(present):
        raise ValueError("The Imperial course installation is incomplete. Reinstall the current GitHub add-on package.")
    if not any(present):
        return load_pack(root / "data" / "tester.json")
    packs = [load_pack(path) for path in paths]
    exercises = [exercise for pack in packs for exercise in pack["exercises"]]
    combined = {"schema_version": 1, "pack_id": "comuls-imperial-french",
                "version": "0.2.0", "cohorts": list(COHORTS),
                "component_packs": [{"pack_id": p["pack_id"], "version": p["version"]} for p in packs],
                "exercises": exercises}
    errors = validate_pack(combined)
    if errors:
        raise ValueError("Invalid Imperial course: " + "; ".join(errors[:10]))
    return combined

def suggested_cohort(root: Path):
    path = root / "course_profile.json"
    if path.is_file():
        value = json.loads(path.read_text(encoding="utf-8")).get("cohort")
        if value in COHORTS:
            return value
    return "B1"

def route_candidates(catalog, stage, repair=False):
    for exercise in catalog:
        origin = exercise.get("cohort", exercise.get("origin_entry_level"))
        if repair or not origin or origin == stage:
            yield exercise

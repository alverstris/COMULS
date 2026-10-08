#!/usr/bin/env python3
"""Read-only structural audit of COMULS's published vocabulary inventory.

This audits observed CSV/JSON fields. It does not relabel vocabulary, generate
cards, reinterpret CEFR labels, or certify that source entries are lesson-ready.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

REQUIRED_HEADERS = ("entry_id", "definition", "senses_json")
TYPE_FIELDS = ("entry_type", "vocabulary_type", "item_type", "type", "kind", "is_expression")
LEVEL_FIELDS = (
    "cefr_level", "cefr", "cefr_band", "level", "lemma_cefr_level",
    "sense_cefr_level", "sense_level", "published_band", "local_intro_stage",
)
LANGUAGE_FIELDS = ("definition_language",)
README_EXPECTED = {"parent_rows": 10407, "sense_records": 24608}


def _increase_csv_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _explicit_boolean(value: Any) -> bool | None:
    if type(value) is bool:
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in ("true", "1"):
            return True
        if normalized in ("false", "0"):
            return False
    if type(value) is int and value in (0, 1):
        return bool(value)
    return None


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON object key: " + key)
        value[key] = item
    return value


def _readiness(value: dict[str, Any]) -> str:
    if "card_ready" not in value:
        return "missing"
    flag = _explicit_boolean(value["card_ready"])
    if flag is True:
        return "true"
    if flag is False:
        return "false"
    return "invalid"


def _classification(row: dict[str, Any], present: list[str]) -> str:
    categories: set[str] = set()
    for field in present:
        value = row.get(field)
        if field == "is_expression":
            flag = _explicit_boolean(value)
            if flag is not None:
                categories.add("expressions" if flag else "word_families")
        elif isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in ("expression", "expressions", "locution", "locutions"):
                categories.add("expressions")
            elif normalized in ("word", "words", "word_family", "word family", "mot"):
                categories.add("word_families")
    if len(categories) > 1:
        return "conflicting_explicit_labels"
    return next(iter(categories), "unknown")


def audit_source(path: str | Path, expected: dict[str, int] | None = None) -> dict[str, Any]:
    """Stream source rows and return a JSON-serializable report.

    Equal repeated IDs are counted and warned about. An ID reused with different
    contents (or a sense ID owned by different parents) is a structural error.
    Unknown optional headers/fields remain visible instead of being invented.
    """
    source = Path(path)
    _increase_csv_limit()
    report: dict[str, Any] = {
        "schema_version": 1,
        "source": {"path": str(source), "sha256": None, "bytes": None},
        "purpose": "Audit unchanged vocabulary inventory; not generated course content.",
        "source_modified": False,
        "headers": [],
        "observed_sense_keys": [],
        "counts": {
            "parent_rows": 0, "unique_parent_ids": 0, "sense_records": 0,
            "unique_sense_ids": 0, "duplicate_parent_id_occurrences": 0,
            "conflicting_parent_id_occurrences": 0, "duplicate_sense_id_occurrences": 0,
            "conflicting_sense_id_occurrences": 0,
        },
        "classification": {
            "status": "unavailable", "explicit_fields_observed": [],
            "counts": {"word_families": 0, "expressions": 0, "unknown": 0,
                       "conflicting_explicit_labels": 0},
        },
        "parent_field_counts": {},
        "sense_field_counts": {},
        "card_ready": {"parents": {}, "senses": {}},
        "json_fields_checked": {},
        "reference_scope": (
            "Embedded alias, realization and relation JSON is parsed without rewriting. "
            "External relationship targets are not assumed to be contained in this inventory."
        ),
        "readme_comparison": {},
        "errors": [], "error_count": 0, "warnings": [],
        "status": "pending",
    }

    def error(message: str) -> None:
        report["error_count"] += 1
        if len(report["errors"]) < 100:
            report["errors"].append(message)

    json_counts: Counter[str] = Counter()
    parent_ready: Counter[str] = Counter()
    sense_ready: Counter[str] = Counter()
    parent_fields: dict[str, Counter[str]] = {}
    sense_fields: dict[str, Counter[str]] = {}
    sense_keys: set[str] = set()
    parent_seen: dict[str, str] = {}
    sense_seen: dict[str, tuple[str, str]] = {}
    type_fields: list[str] = []

    def walk_json(value: Any, location: str, shape: str) -> Any:
        if isinstance(value, list):
            return [walk_json(item, location + "[" + str(index) + "]", shape + "[]")
                    for index, item in enumerate(value)]
        if not isinstance(value, dict):
            return value
        parsed: dict[str, Any] = {}
        for key, item in value.items():
            child_location = location + "." + key
            child_shape = shape + "." + key
            if key.endswith("_json"):
                json_counts[child_shape] += 1
                if isinstance(item, str):
                    if not item.strip():
                        parsed[key] = item
                        continue
                    try:
                        item = json.loads(item, object_pairs_hook=_unique_object)
                    except (ValueError, TypeError) as exc:
                        error(child_location + ": invalid JSON (" + str(exc)[:160] + ")")
                        parsed[key] = item
                        continue
            parsed[key] = walk_json(item, child_location, child_shape)
        return parsed

    def observe_fields(record: dict[str, Any], counters: dict[str, Counter[str]]) -> None:
        for field in LEVEL_FIELDS + LANGUAGE_FIELDS:
            if field in record:
                value = record[field]
                # Exact source labels are retained; B1/B2 is not silently rewritten.
                label = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
                counters.setdefault(field, Counter())[label] += 1

    try:
        digest = hashlib.sha256()
        with source.open("rb") as raw:
            for chunk in iter(lambda: raw.read(1024 * 1024), b""):
                digest.update(chunk)
        report["source"]["sha256"] = digest.hexdigest()
        report["source"]["bytes"] = source.stat().st_size
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            report["headers"] = headers
            for field in REQUIRED_HEADERS:
                if field not in headers:
                    error("Missing required CSV header: " + field)
            if len(headers) != len(set(headers)):
                error("Duplicate CSV headers would overwrite source fields")
            if report["error_count"]:
                report["status"] = "failed"
                return report
            type_fields = [field for field in TYPE_FIELDS if field in headers]
            report["classification"]["explicit_fields_observed"] = type_fields
            for row_index, row in enumerate(reader, start=1):
                location = "parent row " + str(row_index)
                counts = report["counts"]
                counts["parent_rows"] += 1
                if None in row or any(value is None for value in row.values()):
                    error(location + ": CSV field count differs from header count")
                    continue
                parent_id = row.get("entry_id", "").strip()
                if not parent_id:
                    error(location + ": entry_id is missing")
                parsed = walk_json(row, location, "parent")
                row_hash = _fingerprint(parsed)
                if parent_id:
                    if parent_id in parent_seen:
                        counts["duplicate_parent_id_occurrences"] += 1
                        if parent_seen[parent_id] != row_hash:
                            counts["conflicting_parent_id_occurrences"] += 1
                            error(location + ": conflicting entry_id " + parent_id)
                    else:
                        parent_seen[parent_id] = row_hash
                classification = _classification(row, type_fields)
                report["classification"]["counts"][classification] += 1
                parent_ready[_readiness(row)] += 1
                observe_fields(row, parent_fields)
                senses = parsed.get("senses_json")
                if not isinstance(senses, list):
                    error(location + ": senses_json must contain an array")
                    continue
                if not senses:
                    report["warnings"].append(location + ": no selected senses")
                for index, sense in enumerate(senses):
                    sense_location = location + ", sense " + str(index + 1)
                    counts["sense_records"] += 1
                    if not isinstance(sense, dict):
                        error(sense_location + ": selected sense must be an object")
                        continue
                    sense_keys.update(sense)
                    sense_ready[_readiness(sense)] += 1
                    observe_fields(sense, sense_fields)
                    sense_id = sense.get("sense_id")
                    if not isinstance(sense_id, str) or not sense_id.strip():
                        error(sense_location + ": sense_id is missing or is not text")
                        continue
                    sense_id = sense_id.strip()
                    identity = (parent_id, _fingerprint(sense))
                    if sense_id in sense_seen:
                        counts["duplicate_sense_id_occurrences"] += 1
                        if sense_seen[sense_id] != identity:
                            counts["conflicting_sense_id_occurrences"] += 1
                            error(sense_location + ": conflicting sense_id " + sense_id)
                    else:
                        sense_seen[sense_id] = identity
    except (OSError, UnicodeError, csv.Error) as exc:
        error("Cannot read source CSV: " + str(exc))

    report["counts"]["unique_parent_ids"] = len(parent_seen)
    report["counts"]["unique_sense_ids"] = len(sense_seen)
    report["observed_sense_keys"] = sorted(sense_keys)
    report["json_fields_checked"] = dict(sorted(json_counts.items()))
    report["card_ready"]["parents"] = dict(sorted(parent_ready.items()))
    report["card_ready"]["senses"] = dict(sorted(sense_ready.items()))
    report["parent_field_counts"] = {key: dict(sorted(value.items())) for key, value in sorted(parent_fields.items())}
    report["sense_field_counts"] = {key: dict(sorted(value.items())) for key, value in sorted(sense_fields.items())}
    classified = report["classification"]["counts"]
    if type_fields:
        report["classification"]["status"] = "complete" if classified["unknown"] == 0 and classified["conflicting_explicit_labels"] == 0 else "partial"
    if classified["conflicting_explicit_labels"]:
        report["warnings"].append("Some rows have conflicting explicit word/expression labels; those rows were not guessed.")
    if parent_ready["invalid"] or sense_ready["invalid"]:
        report["warnings"].append("Some card_ready values are not explicit booleans; they are not treated as ready.")
    for key in ("duplicate_parent_id_occurrences", "duplicate_sense_id_occurrences"):
        if report["counts"][key]:
            report["warnings"].append(key + ": " + str(report["counts"][key]))
    for key, value in (README_EXPECTED if expected is None else expected).items():
        actual = report["counts"].get(key)
        report["readme_comparison"][key] = {"documented": value, "observed": actual, "matches": actual == value}
        if actual != value:
            report["warnings"].append(key + " differs from README reference; observed source totals remain authoritative.")
    report["status"] = "failed" if report["error_count"] else "passed"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(__file__).resolve().parents[1] / "outputs" / "french_vocabulary_b1_c1.csv")
    parser.add_argument("--out", type=Path, default=Path("dist/source_audit.json"))
    args = parser.parse_args(argv)
    if args.input.resolve() == args.out.resolve():
        parser.error("--out must not overwrite the source CSV")
    report = audit_source(args.input)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

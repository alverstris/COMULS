"""Source inventory audit fixtures; no network and no source rewrites."""
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "audit_sources.py"
SPEC = importlib.util.spec_from_file_location("comuls_source_audit", MODULE_PATH)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def sense(identity="s-1", definition="A selected meaning", **extra):
    return {
        "sense_id": identity, "definition": definition, "card_ready": False,
        "sense_cefr_level": "B1/B2", "sense_aliases_json": "[]", **extra,
    }


def parent(identity="p-1", senses=None, **extra):
    return {
        "entry_id": identity, "definition": "Meaning one,\nmeaning two.",
        "senses_json": json.dumps(senses if senses is not None else [sense()], ensure_ascii=False),
        "card_ready": "false", "cefr_level": "B1/B2", **extra,
    }


class SourceAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "source.csv"

    def write_rows(self, rows, fields=None):
        names = fields or list(dict.fromkeys(key for row in rows for key in row))
        with self.path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=names)
            writer.writeheader()
            writer.writerows(rows)
        return self.path

    def report(self):
        return audit.audit_source(self.path, expected={})

    def test_bom_quoted_commas_embedded_newlines_and_nested_json(self):
        first = sense(definition='A comma, a newline\nand a quote: "bonjour".')
        first["grammatical_realizations_json"] = json.dumps([
            {"form": "écoutées", "construction": "être, puis\nécouter"}
        ], ensure_ascii=False)
        self.write_rows([parent(senses=[first, sense("s-2", "Another selected meaning")])])
        before = self.path.read_bytes()
        report = self.report()
        self.assertEqual(report["status"], "passed", report["errors"])
        self.assertEqual(report["counts"]["parent_rows"], 1)
        self.assertEqual(report["counts"]["sense_records"], 2)
        self.assertEqual(report["counts"]["unique_sense_ids"], 2)
        self.assertIn("grammatical_realizations_json", report["observed_sense_keys"])
        self.assertEqual(report["source"]["sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(self.path.read_bytes(), before)

    def test_labels_are_preserved_and_readiness_is_an_explicit_boolean(self):
        self.write_rows([parent(senses=[sense(card_ready="false"), sense("s-2", card_ready="true")])])
        report = self.report()
        self.assertEqual(report["parent_field_counts"]["cefr_level"], {"B1/B2": 1})
        self.assertEqual(report["sense_field_counts"]["sense_cefr_level"], {"B1/B2": 2})
        self.assertEqual(report["card_ready"]["parents"], {"false": 1})
        self.assertEqual(report["card_ready"]["senses"], {"false": 1, "true": 1})
        self.assertFalse(report["source_modified"])

    def test_expression_counts_use_only_observed_explicit_fields(self):
        self.write_rows([
            parent(entry_type="word"),
            parent("p-2", senses=[sense("s-2")], entry_type="expression"),
        ])
        report = self.report()
        self.assertEqual(report["classification"]["status"], "complete")
        self.assertEqual(report["classification"]["counts"]["word_families"], 1)
        self.assertEqual(report["classification"]["counts"]["expressions"], 1)

    def test_missing_type_is_unavailable_not_guessed_from_text(self):
        self.write_rows([parent(vocabulary="tout à fait")])
        report = self.report()
        self.assertEqual(report["classification"]["status"], "unavailable")
        self.assertEqual(report["classification"]["counts"]["unknown"], 1)
        self.assertEqual(report["classification"]["counts"]["expressions"], 0)

    def test_duplicate_and_conflicting_parent_ids_are_distinct_counts(self):
        item = parent()
        self.write_rows([item, dict(item), dict(item, definition="Changed meaning")])
        report = self.report()
        self.assertEqual(report["counts"]["parent_rows"], 3)
        self.assertEqual(report["counts"]["unique_parent_ids"], 1)
        self.assertEqual(report["counts"]["duplicate_parent_id_occurrences"], 2)
        self.assertEqual(report["counts"]["conflicting_parent_id_occurrences"], 1)
        self.assertEqual(report["status"], "failed")

    def test_identical_duplicate_sense_id_is_reported_without_a_conflict(self):
        self.write_rows([parent(senses=[sense(), sense()])])
        report = self.report()
        self.assertEqual(report["counts"]["sense_records"], 2)
        self.assertEqual(report["counts"]["unique_sense_ids"], 1)
        self.assertEqual(report["counts"]["duplicate_sense_id_occurrences"], 1)
        self.assertEqual(report["counts"]["conflicting_sense_id_occurrences"], 0)
        self.assertEqual(report["status"], "passed")

    def test_conflicting_sense_definition_fails(self):
        self.write_rows([parent(senses=[sense(), sense(definition="A different meaning")])])
        report = self.report()
        self.assertEqual(report["counts"]["duplicate_sense_id_occurrences"], 1)
        self.assertEqual(report["counts"]["conflicting_sense_id_occurrences"], 1)
        self.assertEqual(report["status"], "failed")

    def test_same_sense_id_in_different_parents_is_a_conflict(self):
        self.write_rows([parent(), parent("p-2")])
        report = self.report()
        self.assertEqual(report["counts"]["conflicting_sense_id_occurrences"], 1)

    def test_invalid_embedded_json_fails_and_names_the_field(self):
        self.write_rows([parent(senses=[sense(sense_aliases_json="{broken")])])
        report = self.report()
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any("sense_aliases_json" in error for error in report["errors"]))

    def test_empty_optional_json_is_allowed_and_reference_targets_are_not_invented(self):
        self.write_rows([parent(senses=[sense(
            sense_aliases_json="",
            expression_meaning_relation_ids_json='["external-inventory:sense-9"]',
        )])])
        report = self.report()
        self.assertEqual(report["status"], "passed")
        self.assertIn("parent.senses_json[].expression_meaning_relation_ids_json",
                      report["json_fields_checked"])

    def test_json_duplicate_object_keys_are_rejected(self):
        self.write_rows([parent(senses_json='[{"sense_id":"s-1","sense_id":"s-2"}]')])
        report = self.report()
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any("duplicate JSON object key" in error for error in report["errors"]))

    def test_missing_required_header_fails(self):
        self.write_rows([{"entry_id": "p-1", "definition": "A definition"}])
        report = self.report()
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any("senses_json" in error for error in report["errors"]))

    def test_readme_count_drift_is_informational(self):
        self.write_rows([parent()])
        report = audit.audit_source(self.path)
        self.assertEqual(report["status"], "passed")
        self.assertFalse(report["readme_comparison"]["parent_rows"]["matches"])
        self.assertEqual(report["readme_comparison"]["parent_rows"]["observed"], 1)

    def test_large_json_cell_exceeds_csv_default_limit_safely(self):
        self.write_rows([parent(senses=[sense(definition="é" * 150000)])])
        report = self.report()
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["counts"]["sense_records"], 1)

    def test_cli_writes_report_and_preserves_source(self):
        self.write_rows([parent()])
        before = self.path.read_bytes()
        output = Path(self.directory.name) / "dist" / "audit.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code = audit.main(["--input", str(self.path), "--out", str(output)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["status"], "passed")
        self.assertEqual(self.path.read_bytes(), before)

    def test_cli_refuses_to_overwrite_source(self):
        self.write_rows([parent()])
        before = self.path.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            audit.main(["--input", str(self.path), "--out", str(self.path)])
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

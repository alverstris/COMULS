import importlib.util
import json
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tester_core", ROOT / "addon/core.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

class TesterPackTests(unittest.TestCase):
    def test_all_formats_at_each_entry(self):
        pack = core.load_pack(ROOT / "addon/data/tester.json")
        self.assertEqual(len(pack["exercises"]), 90)
        for stage in core.ENTRY_LEVELS:
            items = [e for e in pack["exercises"] if e["origin_entry_level"] == stage]
            self.assertEqual(len(items), 30)
            self.assertEqual({e["type"] for e in items}, set(core.EXERCISE_TYPES))
            self.assertTrue(all(core.level_eligible(e, stage) for e in items))

    def test_lower_level_repair_available_without_demotion(self):
        pack = core.load_pack(ROOT / "addon/data/tester.json")
        for e in pack["exercises"]:
            if e["origin_entry_level"] == "B1":
                self.assertTrue(core.level_eligible(e, "B2"))
                self.assertTrue(core.level_eligible(e, "C1"))

    def test_no_blind_vocabulary_autogeneration(self):
        pack = core.load_pack(ROOT / "addon/data/tester.json")
        for e in pack["exercises"]:
            self.assertEqual(e["qa"]["level_status"], "provisional")
            self.assertTrue(e["qa"]["ready"])
            self.assertTrue(e["provenance"])
            if e["type"] in core.AUDIO_TYPES:
                self.assertTrue(e["audio_text"])

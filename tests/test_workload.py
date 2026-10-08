"""Evidence-based backlog recovery tests without Anki or Qt."""
import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "addon" / "workload.py"
SPEC = importlib.util.spec_from_file_location("comuls_workload_for_tests", MODULE_PATH)
workload = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workload)


class WorkloadTests(unittest.TestCase):
    def test_initial_overflow_pauses_new_admission(self):
        state = workload.update_backlog({}, 10, 901, 900)
        self.assertTrue(state["pause_new"])
        self.assertEqual(state["backlog_recovery_days"], [])

    def test_equal_budget_does_not_start_a_pause(self):
        state = workload.update_backlog({}, 10, 900, 900)
        self.assertFalse(state["pause_new"])

    def test_two_distinct_completed_study_dates_are_required(self):
        state = workload.update_backlog({}, 10, 1000, 900)
        state = workload.update_backlog(state, 11, 500, 900, completed=True)
        self.assertTrue(state["pause_new"])
        self.assertEqual(state["backlog_recovery_days"], ["11"])
        state = workload.update_backlog(state, 11, 400, 900, completed=True)
        self.assertTrue(state["pause_new"])
        self.assertEqual(state["backlog_recovery_days"], ["11"])
        state = workload.update_backlog(state, 12, 500, 900, completed=True)
        self.assertFalse(state["pause_new"])
        self.assertEqual(state["backlog_recovery_days"], ["11", "12"])

    def test_observation_on_a_new_day_is_not_completed_study_evidence(self):
        state = {"pause_new": True, "backlog_recovery_days": ["11"]}
        observed = workload.update_backlog(state, 12, 100, 900)
        self.assertTrue(observed["pause_new"])
        self.assertEqual(observed["backlog_recovery_days"], ["11"])
        observed = workload.update_backlog(observed, 13, 700, 900, completed=True)
        self.assertTrue(observed["pause_new"])
        self.assertEqual(observed["backlog_recovery_days"], ["11"])

    def test_seventy_percent_boundary_is_not_recovery(self):
        state = {"pause_new": True, "backlog_recovery_days": ["11"]}
        state = workload.update_backlog(state, 12, 630, 900, completed=True)
        self.assertTrue(state["pause_new"])
        self.assertEqual(state["backlog_recovery_days"], ["11"])
        state = workload.update_backlog(state, 12, 629.9, 900, completed=True)
        self.assertFalse(state["pause_new"])

    def test_any_new_overflow_resets_recovery_dates(self):
        state = {"pause_new": True, "backlog_recovery_days": ["11"]}
        state = workload.update_backlog(state, 12, 901, 900)
        self.assertTrue(state["pause_new"])
        self.assertEqual(state["backlog_recovery_days"], [])
        state = workload.update_backlog(state, 13, 400, 900, completed=True)
        self.assertTrue(state["pause_new"])
        self.assertEqual(state["backlog_recovery_days"], ["13"])

    def test_recovered_state_can_pause_again(self):
        state = {"pause_new": False, "backlog_recovery_days": ["11", "12"]}
        state = workload.update_backlog(state, 13, 1000, 900)
        self.assertTrue(state["pause_new"])
        self.assertEqual(state["backlog_recovery_days"], [])

    def test_zero_budget_is_safe_and_does_not_fabricate_recovery(self):
        self.assertFalse(workload.update_backlog({}, 10, 0, 0)["pause_new"])
        self.assertTrue(workload.update_backlog({}, 10, 1, 0)["pause_new"])
        state = {"pause_new": True, "backlog_recovery_days": ["9"]}
        state = workload.update_backlog(state, 10, 0, 0, completed=True)
        self.assertTrue(state["pause_new"])
        self.assertEqual(state["backlog_recovery_days"], ["9"])

    def test_input_and_nested_state_are_not_mutated(self):
        original = {"pause_new": True, "backlog_recovery_days": ["11"],
                    "other": {"values": [1]}, "manual_override_day": 12}
        result = workload.update_backlog(original, 12, 400, 900, completed=True)
        self.assertTrue(original["pause_new"])
        self.assertEqual(original["backlog_recovery_days"], ["11"])
        result["other"]["values"].append(2)
        self.assertEqual(original["other"]["values"], [1])
        self.assertEqual(result["manual_override_day"], 12)

    def test_invalid_numbers_are_rejected_without_modifying_state(self):
        state = {"pause_new": False}
        for due, budget in ((-1, 900), (0, -1), (float("nan"), 900),
                            (1, float("inf")), (True, 900)):
            with self.subTest(due=due, budget=budget), self.assertRaises(ValueError):
                workload.update_backlog(state, 10, due, budget)
        self.assertEqual(state, {"pause_new": False})


if __name__ == "__main__":
    unittest.main()

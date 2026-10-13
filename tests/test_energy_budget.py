import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Test the student's CLI output using the same Python interpreter as the test runner.
SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "energy_budget.py"


class EnergyBudgetTests(unittest.TestCase):
    def run_model(self, states, voltage_v=3.3):
        # Temporary JSON inputs leave the illustrative model in examples/ unchanged.
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "model.json"
            model.write_text(json.dumps({"voltage_v": voltage_v, "states": states}),
                             encoding="utf-8")
            return subprocess.run([sys.executable, str(SCRIPT), str(model)],
                                  capture_output=True, text=True, timeout=10)

    def test_known_duty_cycle(self):
        # One second: 10 ms at 5 mA plus 990 ms at 5 uA gives 54.95 uC.
        result = self.run_model([
            {"duration_s": .01, "current_a": .005},
            {"duration_s": .99, "current_a": .000005}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Average current: 54.950 uA", result.stdout)
        self.assertIn("Charge per period: 54.950 uC", result.stdout)
        self.assertIn("Energy per period: 181.335 uJ", result.stdout)
        self.assertIn("Period: 1.000000 s", result.stdout)

    def test_idle_leak_changes_budget(self):
        # Raising idle current to 100 uA shows how leakage can dominate a long sleep.
        result = self.run_model([
            {"duration_s": .01, "current_a": .005},
            {"duration_s": .99, "current_a": .0001}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Average current: 149.000 uA", result.stdout)

    def test_invalid_inputs(self):
        # Non-finite values and invalid signs must fail before printing an average.
        cases = [
            ([{"duration_s": duration, "current_a": current}], 3.3, field)
            for duration, current, field in [
                (0, 1, "duration_s"), (-1, 1, "duration_s"),
                (math.nan, 1, "duration_s"), (1, -1, "current_a"),
                (1, math.inf, "current_a")]
        ]
        cases += [([], 3.3, "at least one state"),
                  ([{"duration_s": 1, "current_a": 1}], 0, "voltage_v")]
        for states, voltage, message in cases:
            with self.subTest(states=states, voltage=voltage):
                result = self.run_model(states, voltage)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertNotIn("Average current:", result.stdout)


if __name__ == "__main__":
    unittest.main()

"""AEM units, integration, raw capture preservation and offline plotting."""

from contextlib import redirect_stdout
import io
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

# Synthetic fixtures make unit conversions/integration testable without a kit.
TOOLS = Path(__file__).resolve().parents[1] / "tools"
CSV_HEADER = "Timestamp [us], Current [mA], Voltage [V]\n"
# Bounded timestamp jitter distinguishes time weighting without missing windows.
IRREGULAR_CAPTURE = CSV_HEADER + "17000000,0,3.3\n18000000,2,3.3\n19250000,2,3.3\n"
GAPPED_CAPTURE = CSV_HEADER + "0,0,3.3\n100,0,3.3\n100000,1,3.3\n"
UNIFORMLY_DROPPED_CAPTURE = CSV_HEADER + "0,1,3.3\n200,1,3.3\n400,1,3.3\n"
# Vary both current and voltage to catch an assumed fixed supply in power calculations.
VARYING_VOLTAGE_CAPTURE = CSV_HEADER + "0,1,3\n500000,2,2\n1000000,3,1\n"
PLOT_TIMEOUT_S = 30

sys.path.insert(0, str(TOOLS))
import energy_profile


class EnergyProfileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="energy captures with spaces ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def csv(self, content, name="capture.csv"):
        # Include a BOM to exercise the reader's vendor-file encoding support.
        path = self.root / name
        path.write_text(content, encoding="utf-8-sig")
        return path

    def test_units_and_time_weighted_integration(self):
        # Trapezoids give 1 mC + 2.5 mC over 2.25 s, with no missing windows.
        data = energy_profile.read_capture(self.csv(IRREGULAR_CAPTURE))
        self.assertEqual(data[0], [0.0, 1.0, 2.25])
        result = energy_profile.summarize(*data)
        self.assertEqual(result["samples"], 3)
        self.assertEqual(result["duration_s"], 2.25)
        self.assertFalse(result["gap_indices"])
        self.assertAlmostEqual(result["average_current_ua"], 3500 / 2.25)
        self.assertAlmostEqual(result["average_power_mw"], 11.55 / 2.25)
        self.assertAlmostEqual(result["charge_uc"], 3500)
        self.assertAlmostEqual(result["energy_uj"], 11550)

    def test_missing_samples_withhold_totals_and_report_gap_extent(self):
        data = energy_profile.read_capture(self.csv(GAPPED_CAPTURE))
        result = energy_profile.summarize(*data)
        self.assertEqual(result["gap_indices"], [1])
        self.assertAlmostEqual(result["missing_duration_s"], 0.0998)
        self.assertAlmostEqual(result["maximum_interval_s"], 0.0999)
        for metric in ("average_current_ua", "average_power_mw", "charge_uc", "energy_uj"):
            self.assertIsNone(result[metric])

    def test_requested_rate_detects_uniformly_missing_windows(self):
        data = energy_profile.read_capture(self.csv(UNIFORMLY_DROPPED_CAPTURE))
        # Timestamps alone cannot distinguish uniform loss from a lower logging rate.
        self.assertFalse(energy_profile.summarize(*data)["gap_indices"])
        result = energy_profile.summarize(*data, rate=10000)
        self.assertEqual(result["gap_indices"], [0, 1])
        self.assertAlmostEqual(result["missing_duration_s"], 0.0002)
        self.assertIsNone(result["energy_uj"])
        for rate in (0, -1, math.nan, math.inf):
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                energy_profile.summarize(*data, rate=rate)

    def test_gap_plot_breaks_both_traces_and_warns(self):
        path = self.csv(GAPPED_CAPTURE)
        output = io.StringIO()
        with patch("matplotlib.figure.Figure.savefig", autospec=True) as savefig, \
             redirect_stdout(output):
            energy_profile.plot([path])
        figure = savefig.call_args.args[0]
        for axis in figure.axes:
            values = axis.lines[0].get_ydata()
            self.assertEqual(sum(math.isnan(value) for value in values), 1)
        self.assertIn("WARNING: 1 sample gaps", output.getvalue())
        self.assertIn("99.900 ms", output.getvalue())
        self.assertIn("energy are unavailable", output.getvalue())
        self.assertNotIn("Average current:", output.getvalue())
        self.assertNotIn("Charge:", output.getvalue())

    def test_plot_cli_checks_original_rate_and_preserves_raw_capture(self):
        path = self.csv(UNIFORMLY_DROPPED_CAPTURE)
        raw = path.read_bytes()
        png = self.root / "missing.png"
        env = os.environ.copy()
        env["MPLCONFIGDIR"] = str(self.root / "matplotlib")
        result = subprocess.run([sys.executable, str(TOOLS / "energy_profile.py"), "plot",
            str(path), "--rate", "10000", "--output", str(png)], cwd=self.root, env=env,
            capture_output=True, text=True, timeout=PLOT_TIMEOUT_S)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WARNING: 2 sample gaps", result.stdout)
        self.assertNotIn("Average current:", result.stdout)
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(png.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_power_uses_each_samples_voltage(self):
        data = energy_profile.read_capture(self.csv(VARYING_VOLTAGE_CAPTURE))
        result = energy_profile.summarize(*data)
        self.assertAlmostEqual(result["average_current_ua"], 2000)
        self.assertAlmostEqual(result["average_power_mw"], 3.5)
        self.assertAlmostEqual(result["energy_uj"], 3500)

    def test_signed_measurement_noise_is_preserved(self):
        # Equal positive/negative noise cancels; clamping would create false charge.
        data = energy_profile.read_capture(self.csv(CSV_HEADER + "0,-0.001,3.3\n1000000,0.001,3.3\n"))
        self.assertEqual(data[1], [-0.001, 0.001])
        self.assertAlmostEqual(energy_profile.summarize(*data)["charge_uc"], 0)

    def test_invalid_csv_is_rejected(self):
        cases = [("", "expected Commander"),
                 (CSV_HEADER + "0,1,3.3\n", "at least two"),
                 (CSV_HEADER.replace("[mA]", "[A]"), "expected Commander"),
                 (CSV_HEADER + "0,1,3.3\n0,2,3.3\n", "timestamps must increase"),
                 (CSV_HEADER + "100,1,3.3\n0,2,3.3\n", "timestamps must increase"),
                 (CSV_HEADER + "0,nan,3.3\n100,2,3.3\n", "non-finite"),
                 (CSV_HEADER + "0,1,inf\n100,2,3.3\n", "non-finite"),
                 (CSV_HEADER + "0,1\n100,2,3.3\n", "invalid numeric")]
        for content, message in cases:
            with self.subTest(content=content), self.assertRaisesRegex(ValueError, message):
                energy_profile.read_capture(self.csv(content))

    def test_capture_preserves_vendor_csv_and_passes_literal_paths(self):
        output = self.root / "new captures/kit.csv"
        commander = self.root / "vendor tools/commander.exe"
        commands = []

        def dump(command, **kwargs):
            # Stand in for Commander, writing its raw CSV without any USB access.
            commands.append(command)
            destination = Path(command[command.index("--outfile") + 1])
            destination.write_bytes(IRREGULAR_CAPTURE.encode("utf-8"))
            return subprocess.CompletedProcess(command, 0)

        with patch.object(energy_profile.firmware, "tools", return_value={"commander": commander}), \
             patch.object(energy_profile.subprocess, "run", side_effect=dump), redirect_stdout(io.StringIO()):
            energy_profile.capture(output, 4.5, 1000, "kit serial with spaces")
        self.assertEqual(output.read_bytes(), IRREGULAR_CAPTURE.encode("utf-8"))
        self.assertEqual(commands[0][0], str(commander))
        self.assertEqual(commands[0][1:3], ["aem", "dump"])
        self.assertIn(str(output.resolve()), commands[0])
        self.assertEqual(commands[0][-2:], ["--serialno", "kit serial with spaces"])

    def test_existing_capture_and_invalid_options_do_not_touch_kit(self):
        # Validation should finish before installed-tool discovery or acquisition.
        existing = self.csv(IRREGULAR_CAPTURE)
        with patch.object(energy_profile.firmware, "tools") as tools:
            with self.assertRaises(FileExistsError):
                energy_profile.capture(existing, 10, 1000)
            for seconds, rate in [(0, 1000), (-1, 1000), (float("nan"), 1000), (10, 0)]:
                with self.subTest(seconds=seconds, rate=rate), self.assertRaises(ValueError):
                    energy_profile.capture(self.root / "new.csv", seconds, rate)
            tools.assert_not_called()
        self.assertEqual(existing.read_text(encoding="utf-8-sig"), IRREGULAR_CAPTURE)

    def test_plot_cli_compares_files_offline_without_display(self):
        # A separate process checks the actual CLI and headless PNG output.
        first = self.csv(IRREGULAR_CAPTURE, "first.csv")
        second = self.csv(VARYING_VOLTAGE_CAPTURE, "second.csv")
        output = self.root / "plots/comparison.png"
        env = os.environ.copy()
        # Keep Matplotlib's cache within the disposable test directory.
        env["MPLCONFIGDIR"] = str(self.root / "matplotlib")
        result = subprocess.run([sys.executable, str(TOOLS / "energy_profile.py"), "plot",
            str(first), str(second), "--output", str(output)], cwd=self.root, env=env,
            capture_output=True, text=True, timeout=PLOT_TIMEOUT_S)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1555.556 uA", result.stdout)
        self.assertIn("2000.000 uA", result.stdout)
        self.assertEqual(output.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()

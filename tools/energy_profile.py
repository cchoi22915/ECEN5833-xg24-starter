#!/usr/bin/env python3
"""Capture Pro Kit AEM data to CSV and plot saved captures."""

import argparse
import csv
from itertools import pairwise
import math
from pathlib import Path
from statistics import median_low
import subprocess
import sys

import firmware

# Capture defaults and plot settings; CLI options override duration and sample rate.
DEFAULT_SECONDS = 10.0
DEFAULT_RATE_HZ = 10000
CAPTURE_TIMEOUT_MARGIN_S = 30
# Commander exports microseconds, milliamps and volts. Preserve these CSV units.
CSV_HEADER = ("Timestamp [us]", "Current [mA]", "Voltage [V]")
MICROSECONDS_PER_SECOND = 1_000_000
MICRO_PER_MILLI = 1000
FIGURE_SIZE = (10, 6)
PLOT_DPI = 150
COMPARISON_NAME = "comparison.png"
# Allow timestamp jitter, but never integrate across a missing logging window.
GAP_INTERVAL_FACTOR = 1.5


def read_capture(path):
    # utf-8-sig accepts a vendor CSV with or without a byte-order mark.
    times, currents, voltages = [], [], []
    with path.open(newline="", encoding="utf-8-sig") as source:
        rows = csv.reader(source)
        header = next(rows, [])
        if tuple(field.strip() for field in header) != CSV_HEADER:
            raise ValueError(f"{path}: expected Commander CSV columns: {', '.join(CSV_HEADER)}")
        for line, row in enumerate(rows, 2):
            if not row:
                continue
            try:
                timestamp, current, voltage = map(float, row)
            except ValueError as exc:
                raise ValueError(f"{path}: invalid numeric data on line {line}") from exc
            if not all(math.isfinite(value) for value in (timestamp, current, voltage)):
                raise ValueError(f"{path}: non-finite data on line {line}")
            # Integration needs positive time intervals between successive samples.
            if times and timestamp <= times[-1]:
                raise ValueError(f"{path}: timestamps must increase (line {line})")
            times.append(timestamp)
            # Retain signed samples: clamping small measurement noise would bias charge.
            currents.append(current)
            voltages.append(voltage)
    if len(times) < 2:
        raise ValueError(f"{path}: at least two samples are required")
    # Convert only time to seconds and show elapsed time from the first sample.
    origin = times[0]
    return [(time - origin) / MICROSECONDS_PER_SECOND for time in times], currents, voltages


def summarize(times, currents, voltages, rate=None):
    # Use actual intervals, which may vary, instead of an unweighted sample average.
    intervals = [end - start for start, end in pairwise(times)]
    if rate is not None and (not math.isfinite(rate) or rate <= 0):
        raise ValueError("--rate must be positive and finite")
    # Capture knows its requested rate; saved files use their typical interval.
    nominal_interval = 1 / rate if rate is not None else median_low(intervals)
    gaps = [index for index, dt in enumerate(intervals)
            if dt > nominal_interval * GAP_INTERVAL_FACTOR]
    duration = times[-1] - times[0]
    result = {"samples": len(times), "duration_s": duration, "gap_indices": gaps,
              "missing_duration_s": sum(intervals[index] - nominal_interval for index in gaps),
              "maximum_interval_s": max(intervals),
              "average_current_ua": None, "average_power_mw": None,
              "charge_uc": None, "energy_uj": None}
    # Unknown intervals cannot support full-capture averages or energy totals.
    if gaps:
        return result
    # mA * V = mW; use each sample's measured voltage rather than an assumed supply.
    powers = [current * voltage for current, voltage in zip(currents, voltages)]
    # Trapezoids approximate the area under current/power between sample pairs.
    # mA * s = mC and mW * s = mJ; convert to micro-units when reporting.
    charge_mc = sum((start + end) * 0.5 * dt
                    for (start, end), dt in zip(pairwise(currents), intervals))
    energy_mj = sum((start + end) * 0.5 * dt
                    for (start, end), dt in zip(pairwise(powers), intervals))
    result.update(average_current_ua=charge_mc / duration * MICRO_PER_MILLI,
                  average_power_mw=energy_mj / duration,
                  charge_uc=charge_mc * MICRO_PER_MILLI,
                  energy_uj=energy_mj * MICRO_PER_MILLI)
    return result


def report(path, data, rate=None):
    # Preserve raw samples, but withhold totals when their time span has gaps.
    result = summarize(*data, rate=rate)
    print(f"{path}: {result['samples']} samples, {result['duration_s']:.6f} s")
    if result["gap_indices"]:
        print(f"  WARNING: {len(result['gap_indices'])} sample gaps; approximately "
              f"{result['missing_duration_s']:.6f} s missing "
              f"(largest interval {result['maximum_interval_s'] * 1000:.3f} ms).")
        print("  Full-capture averages, charge and energy are unavailable. Recapture before comparing energy.")
        return result
    print(f"  Average current: {result['average_current_ua']:.3f} uA")
    print(f"  Average power: {result['average_power_mw']:.6f} mW")
    print(f"  Charge: {result['charge_uc']:.3f} uC; energy: {result['energy_uj']:.3f} uJ")
    return result


def capture(output, seconds, rate, serial=None):
    # Validate before accessing the kit, and keep existing captures intact.
    if not math.isfinite(seconds) or seconds <= 0 or rate <= 0:
        raise ValueError("--seconds and --rate must be positive, finite values")
    if output.suffix.lower() != ".csv":
        raise ValueError("Capture output must end in .csv")
    if output.exists():
        raise FileExistsError(f"Capture already exists: {output}. Choose a new filename.")
    commander = firmware.tools()["commander"]
    output.parent.mkdir(parents=True, exist_ok=True)
    # Commander owns USB acquisition and writes the raw CSV used by later plots.
    command = [str(commander), "aem", "dump", "--outfile", str(output.resolve()),
               "--duration", str(seconds), "--datarate", str(rate)]
    # Select one debugger when several kits are connected.
    if serial:
        command += ["--serialno", serial]
    print(f"Capturing {seconds:g} s at {rate} Hz to {output} ...", flush=True)
    subprocess.run(command, check=True, timeout=seconds + CAPTURE_TIMEOUT_MARGIN_S)
    report(output, read_capture(output), rate=rate)


def plot(paths, output=None, rate=None):
    # Load plotting only when requested. Agg saves PNGs without a GUI or connected kit.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if output is None:
        output = paths[0].with_suffix(".png") if len(paths) == 1 else paths[0].parent / COMPARISON_NAME
    if output.suffix.lower() != ".png":
        raise ValueError("Plot output must end in .png")
    captures = [(path, read_capture(path)) for path in paths]
    # Shared elapsed time and matching colors make current/power traces comparable.
    figure, axes = plt.subplots(2, 1, sharex=True, figsize=FIGURE_SIZE, layout="constrained")
    for path, data in captures:
        times, currents, voltages = data
        result = report(path, data, rate=rate)
        gaps = set(result["gap_indices"])
        plot_times, plot_currents, plot_powers = [], [], []
        for index, (time, current, voltage) in enumerate(zip(times, currents, voltages)):
            if index - 1 in gaps:
                # NaNs break both traces instead of drawing invented ramps.
                plot_times.append(math.nan)
                plot_currents.append(math.nan)
                plot_powers.append(math.nan)
            plot_times.append(time)
            plot_currents.append(current)
            plot_powers.append(current * voltage)
        marker = "." if gaps else None
        line, = axes[0].plot(plot_times, plot_currents, label=path.stem, linewidth=0.8,
                             marker=marker, markersize=2)
        axes[1].plot(plot_times, plot_powers, color=line.get_color(), linewidth=0.8,
                     marker=marker, markersize=2)
        if gaps:
            figure.suptitle("Missing samples: energy totals unavailable")
    axes[0].set_ylabel("Current (mA)")
    axes[1].set_ylabel("Power (mW)")
    axes[1].set_xlabel("Time from capture start (s)")
    axes[0].legend()
    for axis in axes:
        axis.grid(True, alpha=0.3)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=PLOT_DPI)
    plt.close(figure)
    print(f"Saved {output}")


def main():
    # Capture is a hardware operation; plotting works offline on previously saved CSVs.
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    recording = commands.add_parser("capture", help="save current/voltage samples from the kit")
    recording.add_argument("output", type=Path, help="new CSV filename")
    recording.add_argument("--seconds", type=float, default=DEFAULT_SECONDS)
    recording.add_argument("--rate", type=int, default=DEFAULT_RATE_HZ, help="logging rate in Hz")
    recording.add_argument("--serial", help="J-Link serial number, if multiple kits are connected")
    plotting = commands.add_parser("plot", help="plot one or more saved CSV captures")
    plotting.add_argument("files", type=Path, nargs="+")
    plotting.add_argument("--output", type=Path, help="PNG filename")
    plotting.add_argument("--rate", type=int,
                          help="original logging rate in Hz; otherwise infer the typical interval")
    args = parser.parse_args()
    if args.command == "capture":
        capture(args.output, args.seconds, args.rate, args.serial)
    else:
        plot(args.files, args.output, args.rate)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Energy profiling error: {exc}", file=sys.stderr)
        raise SystemExit(1)

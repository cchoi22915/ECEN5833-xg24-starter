#!/usr/bin/env python3
"""Calculate a state-duration model, not a measured board performance claim."""
import argparse
import json
import math
from pathlib import Path


# The JSON input describes one repeated period using seconds, amps and volts.
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("model", type=Path)
args = parser.parse_args()
model = json.loads(args.model.read_text(encoding="utf-8"))

# This simple model assumes one constant supply voltage for every state.
voltage_v = float(model["voltage_v"])
states = model["states"]
if not math.isfinite(voltage_v) or voltage_v <= 0:
    raise ValueError("voltage_v must be finite and positive")
if not states:
    raise ValueError("at least one state is required")

# Add state durations and charge. A * s = C; average current is total C / total s.
duration = 0.0
charge = 0.0
for state in states:
    seconds = float(state["duration_s"])
    amps = float(state["current_a"])
    # Reject invalid model inputs before producing a numerical result.
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("each duration_s must be finite and positive")
    if not math.isfinite(amps) or amps < 0:
        raise ValueError("each current_a must be finite and nonnegative")
    duration += seconds
    charge += seconds * amps

# Convert SI values to micro-units for display; energy at constant voltage is Q * V.
print(model.get("description", "State-duration energy model"))
print(f"Average current: {charge / duration * 1e6:.3f} uA")
print(f"Charge per period: {charge * 1e6:.3f} uC")
print(f"Energy per period: {charge * voltage_v * 1e6:.3f} uJ")
print(f"Period: {duration:.6f} s")

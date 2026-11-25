"""Offline R18 two-channel neutral-display timing. No acquisition or H1 runner."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

STUDY = "GAZEBLOOM_R18_TWO_CHANNEL_BENCH_V1"
MAX_GAP_MS = 2.0
HOLD_MS = 50.0
TOL = 0.10
FIELDS = {"study", "source_kind", "shared_acquisition_clock_declared",
          "trigger_low", "trigger_high", "optical_active", "optical_neutral",
          "trace_sha256", "instrument_reference", "trigger_reference",
          "display_reference", "human_participants", "camera_used",
          "experimental_images_used"}


def number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name}: finite number required")
    return float(value)


def normalize(value, low, high):
    result = (value - low) / (high - low)
    if not math.isfinite(result):
        raise ValueError("normalized value is nonfinite")
    return result


def analyze(meta: dict, raw: bytes) -> dict:
    if not isinstance(meta, dict) or set(meta) != FIELDS:
        raise ValueError("metadata fields mismatch")
    if meta["study"] != STUDY or meta["source_kind"] not in ("SYNTHETIC", "DECLARED_BENCH_CAPTURE"):
        raise ValueError("study/source mismatch")
    if (meta["shared_acquisition_clock_declared"] is not True
            or type(meta["human_participants"]) is not int or meta["human_participants"] != 0
            or meta["camera_used"] is not False or meta["experimental_images_used"] is not False):
        raise ValueError("one declared shared clock and neutral no-human bench required")
    for field in ("instrument_reference", "trigger_reference", "display_reference"):
        v = meta[field]
        if not isinstance(v, str) or not 3 <= len(v.strip()) <= 240:
            raise ValueError(f"missing reference: {field}")
    digest = hashlib.sha256(raw).hexdigest()
    if meta["trace_sha256"] != digest:
        raise ValueError("trace fingerprint mismatch")
    tl, th, oa, on = (number(meta[k], k) for k in
                       ("trigger_low", "trigger_high", "optical_active", "optical_neutral"))
    if (not math.isfinite(th-tl) or th-tl <= 1e-9
            or not math.isfinite(oa-on) or abs(oa-on) <= 1e-9):
        raise ValueError("invalid reference separation")
    if len(raw) > 64_000_000:
        raise ValueError("trace too large")
    reader = csv.DictReader(raw.decode("utf-8-sig").splitlines(), strict=True)
    if reader.fieldnames != ["timestamp_ms", "trigger_signal", "photodiode_signal"]:
        raise ValueError("invalid CSV columns")
    rows = []
    for row in reader:
        if len(rows) >= 1_000_000 or None in row:
            raise ValueError("invalid row count/shape")
        try:
            t, v, p = (float(row[k]) for k in reader.fieldnames)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid numeric CSV") from exc
        if not all(map(math.isfinite, (t, v, p))):
            raise ValueError("nonfinite sample")
        if rows and t <= rows[-1][0]:
            raise ValueError("timestamps must increase strictly")
        rows.append((t, normalize(v, tl, th), normalize(p, on, oa)))
    if len(rows) < 10:
        raise ValueError("at least ten rows required")
    report = {
        "study": STUDY, "source_kind": meta["source_kind"], "trace_sha256": digest,
        "sample_count": len(rows), "max_sample_gap_ms": max(b[0]-a[0] for a,b in zip(rows, rows[1:])),
        "trigger_bracket_ms": None, "optical_bracket_ms": None, "latency_bracket_ms": None,
        "measured_endpoint": "external electrical marker threshold to local photodiode neutral-band entry",
        "clock_and_calibration_verified": False, "physical_provenance_verified": False,
        "safety_threshold_certified": False, "human_exposure_authorized": False,
        "human_participants": 0, "camera_used": False, "experimental_images_used": False,
    }

    def finish(state):
        report["state"] = state
        return report

    if report["max_sample_gap_ms"] > MAX_GAP_MS:
        return finish("INSUFFICIENT_SAMPLE_RESOLUTION")
    edges = [i for i in range(1, len(rows)) if rows[i-1][1] < .5 <= rows[i][1]]
    if len(edges) != 1:
        return finish("AMBIGUOUS_TRIGGER")
    i = edges[0]
    # Require baseline low before the edge and stable high after it.
    # A gradual marker or bounce is intentionally not accepted by v1.
    if (i < 5 or len(rows)-i < 5
            or any(abs(r[1]) > TOL for r in rows[:i])
            or any(abs(r[1]-1) > TOL for r in rows[i:])):
        return finish("AMBIGUOUS_TRIGGER")
    edge_lo, edge_hi = rows[i-1][0], rows[i][0]
    report["trigger_bracket_ms"] = [edge_lo, edge_hi]
    if any(abs(r[2]-1) > TOL for r in rows[i-5:i]):
        return finish("ACTIVE_BASELINE_NOT_CONFIRMED")
    if abs(rows[i][2]) <= TOL:
        return finish("ORDER_AMBIGUOUS")
    j = next((k for k in range(i+1, len(rows)) if abs(rows[k][2]) <= TOL), None)
    if j is None:
        return finish("RIGHT_CENSORED_NO_NEUTRAL")
    if any(abs(r[2]) > TOL for r in rows[j:]):
        return finish("REBOUND_OR_OVERSHOOT")
    light_lo, light_hi = rows[j-1][0], rows[j][0]
    if rows[-1][0]-light_hi < HOLD_MS or len(rows)-j < 3:
        return finish("INSUFFICIENT_NEUTRAL_FOLLOWUP")
    report["optical_bracket_ms"] = [light_lo, light_hi]
    # Both electrical and optical edges are sampled, not exact timestamps.
    report["latency_bracket_ms"] = [light_lo-edge_hi, light_hi-edge_lo]
    return finish("SAMPLED_MARKER_TO_LIGHT_BRACKET__NOT_CERTIFIED")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--metadata", type=Path, required=True)
    p.add_argument("--trace", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    result = analyze(json.loads(args.metadata.read_text(encoding="utf-8")), args.trace.read_bytes())
    payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+"\n"
    with args.out.open("x", encoding="utf-8") as stream:
        stream.write(payload)
    print(payload, end="")


if __name__ == "__main__":
    main()

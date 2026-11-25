#!/usr/bin/env python3
"""R17 offline optical STOP trace audit.

NO sensor, camera, participant runner, research PNG or GUI is operated here.
Synthetic traces exercise the parser only. Declared real traces are not
automatically accepted as verified physical measurements or safety evidence.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
import math
from pathlib import Path

STUDY = "GAZEBLOOM_R17_OPTICAL_STOP_TRACE_AUDIT_V1"
REQUIRED = {"study", "source_kind", "clock_domain", "shared_clock_claimed",
            "stop_event_ms", "active_reference", "neutral_reference",
            "instrument_reference", "display_reference", "trace_sha256",
            "human_participants", "camera_used", "experimental_images_used"}
KINDS = {"SYNTHETIC", "DECLARED_PHOTODIODE_CAPTURE"}
CONFIRM = 3
THRESHOLD = 0.10
MAX_BRACKET_MS = 20.0


def _number(value: object, field: str) -> float:
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(value)):
        raise ValueError(f"{field}: finite number required")
    return float(value)


def validate_manifest(manifest: dict, raw_csv: bytes) -> dict:
    if not isinstance(manifest, dict) or set(manifest) != REQUIRED:
        raise ValueError("manifest contract fields do not match R17")
    if manifest["study"] != STUDY or manifest["source_kind"] not in KINDS:
        raise ValueError("study or source kind mismatch")
    if manifest["clock_domain"] != "SINGLE_ACQUISITION_CLOCK":
        raise ValueError("event and sensor require one declared acquisition clock")
    if manifest["shared_clock_claimed"] is not True:
        raise ValueError("shared acquisition clock must be explicitly claimed")
    if (manifest["human_participants"] != 0 or manifest["camera_used"] is not False
            or manifest["experimental_images_used"] is not False):
        raise ValueError("R17 excludes participants, cameras and experimental images")
    for field in ("instrument_reference", "display_reference"):
        val = manifest[field]
        if not isinstance(val, str) or len(val.strip()) < 3 or len(val) > 240:
            raise ValueError(f"{field}: informative nonempty reference required")
    stop = _number(manifest["stop_event_ms"], "stop_event_ms")
    if stop < 0:
        raise ValueError("stop event time must be nonnegative")
    active = _number(manifest["active_reference"], "active_reference")
    neutral = _number(manifest["neutral_reference"], "neutral_reference")
    if abs(active-neutral) < 1e-9:
        raise ValueError("active and neutral references must be separated")
    digest = sha256(raw_csv).hexdigest()
    if manifest["trace_sha256"] != digest:
        raise ValueError("CSV content fingerprint mismatch")
    return {"stop": stop, "active": active, "neutral": neutral, "digest": digest}


def parse_samples(raw_csv: bytes) -> list[tuple[float, float]]:
    try:
        txt = raw_csv.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("CSV must be UTF-8") from exc
    reader = csv.DictReader(txt.splitlines(), strict=True)
    if reader.fieldnames != ["timestamp_ms", "photodiode_signal"]:
        raise ValueError("required CSV columns: timestamp_ms,photodiode_signal")
    rows = []
    for row in reader:
        if len(rows) >= 1_000_000 or None in row:
            raise ValueError("row count exceeded or malformed CSV")
        try:
            t = float(row["timestamp_ms"])
            v = float(row["photodiode_signal"])
        except (TypeError, ValueError) as exc:
            raise ValueError("nonnumeric sample") from exc
        if not math.isfinite(t) or not math.isfinite(v) or t < 0:
            raise ValueError("sample times and signals must be finite and nonnegative time")
        if rows and t <= rows[-1][0]:
            raise ValueError("timestamps must be strictly increasing")
        rows.append((t,v))
    if len(rows) < 10:
        raise ValueError("minimum ten samples required")
    return rows


def audit(manifest: dict, raw_csv: bytes) -> dict:
    cfg = validate_manifest(manifest, raw_csv)
    samples = parse_samples(raw_csv)
    stop, active, neutral = cfg["stop"], cfg["active"], cfg["neutral"]
    before = [(t,v) for t,v in samples if t < stop]
    after = [(t,v) for t,v in samples if t >= stop]
    if len(before) < 5 or len(after) < 5:
        raise ValueError("need five samples before and after STOP")
    fraction = lambda v: (v-neutral)/(active-neutral)
    # A real pre-STOP optical state must be observed, not invented by references.
    if any(fraction(v) < 0.9 or fraction(v) > 1.1 for _,v in before[-5:]):
        raise ValueError("pre-STOP optical active baseline not confirmed")
    # If the first post-event sample is already neutral, the transition could
    # have occurred before STOP: do not manufacture a causal STOP delay.
    first_post = fraction(after[0][1])
    status = "RIGHT_CENSORED_NO_CONFIRMED_NEUTRAL"
    bounds = None
    if first_post <= THRESHOLD:
        status = "AMBIGUOUS_ALREADY_NEUTRAL_AT_FIRST_POST_SAMPLE"
    else:
        for i in range(1, len(after)-CONFIRM+1):
            candidate = after[i:i+CONFIRM]
            if all(fraction(v) <= THRESHOLD for _,v in candidate):
                previous_t = after[i-1][0]
                first_neutral_t = candidate[0][0]
                if first_neutral_t-previous_t > MAX_BRACKET_MS:
                    status = "INSUFFICIENT_TIME_RESOLUTION"
                else:
                    status = "DETECTED_SAMPLE_BRACKET__NOT_CERTIFIED"
                    bounds = {"latency_lower_ms": previous_t-stop,
                              "latency_upper_ms": first_neutral_t-stop,
                              "uncertainty_at_least_ms": first_neutral_t-previous_t}
                break
    return {
        "study": STUDY, "input_source_kind": manifest["source_kind"],
        "trace_sha256": cfg["digest"], "samples": len(samples), "state": status,
        "sample_bracket": bounds,
        "shared_clock": "DECLARED_ONLY__NOT_INDEPENDENTLY_VERIFIED",
        "reference_levels": "DECLARED_ONLY__NOT_CALIBRATION_VERIFIED",
        "measurement": "photodiode threshold crossing relative to declared STOP timestamp",
        "threshold_fraction_remaining": THRESHOLD, "consecutive_samples": CONFIRM,
        "physical_provenance_verified": False, "safety_threshold_certified": False,
        "human_exposure_authorized": False, "h1_runner_available": False,
        "human_participants": 0, "camera_used": False,
        "experimental_images_used": False,
        "interpretation": "Candidate optical trace bracket only; no causal timing, calibrated luminance, hardware safety or accommodation claims",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(json.loads(args.manifest.read_text(encoding="utf-8")),
                   args.trace.read_bytes())
    with args.out.open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2, ensure_ascii=False, sort_keys=True)
        out.write("\n")
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

"""All captures are synthetic; no monitor or instrument is measured."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from two_channel import STUDY, analyze


def fixture(mode="normal"):
    lines = ["timestamp_ms,trigger_signal,photodiode_signal"]
    for t in range(-10, 101):
        if mode == "gap" and 20 <= t <= 23:
            continue
        if mode == "short" and t > 40:
            break
        marker = int(t >= 0)
        light = int(t < 18)
        if mode == "no_edge":
            marker = 0
        elif mode == "bounce" and t in (4, 5):
            marker = 0
        elif mode == "early":
            light = int(t < 0)
        elif mode == "censored":
            light = 1
        elif mode == "rebound" and t >= 30:
            light = 1
        elif mode == "overshoot" and t >= 30:
            light = -.5
        elif mode == "inverted":
            light = 1-light
        lines.append(f"{t},{marker},{light}")
    raw = ("\n".join(lines)+"\n").encode()
    meta = {"study": STUDY, "source_kind": "SYNTHETIC",
            "shared_acquisition_clock_declared": True, "trigger_low": 0, "trigger_high": 1,
            "optical_active": 0 if mode=="inverted" else 1,
            "optical_neutral": 1 if mode=="inverted" else 0,
            "trace_sha256": hashlib.sha256(raw).hexdigest(),
            "instrument_reference": "synthetic generator",
            "trigger_reference": "synthetic external edge",
            "display_reference": "no physical display", "human_participants": 0,
            "camera_used": False, "experimental_images_used": False}
    return meta, raw


class BenchTests(unittest.TestCase):
    def test_both_edges_have_uncertainty(self):
        result = analyze(*fixture())
        self.assertEqual(result["state"], "SAMPLED_MARKER_TO_LIGHT_BRACKET__NOT_CERTIFIED")
        self.assertEqual(result["trigger_bracket_ms"], [-1, 0])
        self.assertEqual(result["optical_bracket_ms"], [17, 18])
        self.assertEqual(result["latency_bracket_ms"], [17, 19])
        self.assertFalse(result["physical_provenance_verified"])
        self.assertFalse(result["human_exposure_authorized"])

    def test_inverted_sensor_supported(self):
        self.assertEqual(analyze(*fixture("inverted"))["latency_bracket_ms"], [17, 19])

    def test_ambiguous_or_failed_traces(self):
        for mode, state in (
                ("gap", "INSUFFICIENT_SAMPLE_RESOLUTION"), ("short", "INSUFFICIENT_NEUTRAL_FOLLOWUP"),
                ("no_edge", "AMBIGUOUS_TRIGGER"), ("bounce", "AMBIGUOUS_TRIGGER"),
                ("early", "ORDER_AMBIGUOUS"), ("censored", "RIGHT_CENSORED_NO_NEUTRAL"),
                ("rebound", "REBOUND_OR_OVERSHOOT"), ("overshoot", "REBOUND_OR_OVERSHOOT")):
            with self.subTest(mode=mode):
                result = analyze(*fixture(mode))
                self.assertEqual(result["state"], state)
                self.assertIsNone(result["latency_bracket_ms"])

    def test_metadata_and_hash_rejected(self):
        for field, value in (("camera_used", True), ("human_participants", False),
                             ("experimental_images_used", True),
                             ("shared_acquisition_clock_declared", False),
                             ("trace_sha256", "wrong"), ("optical_active", 0)):
            m, raw = fixture()
            m[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                analyze(m, raw)

    def test_malformed_trace_rejected_even_with_matching_hash(self):
        for suffix in (b"100,1,0\n", b"101,1,nan\n", b"101,1,0,extra\n"):
            m, raw = fixture()
            raw += suffix
            m["trace_sha256"] = hashlib.sha256(raw).hexdigest()
            with self.assertRaises(ValueError):
                analyze(m, raw)

    def test_declared_bench_not_certified(self):
        m, raw = fixture()
        m["source_kind"] = "DECLARED_BENCH_CAPTURE"
        d = analyze(m, raw)
        self.assertFalse(d["clock_and_calibration_verified"])
        self.assertFalse(d["safety_threshold_certified"])

    def test_cli_write_once(self):
        m, raw = fixture()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p/"meta.json").write_text(json.dumps(m))
            (p/"trace.csv").write_bytes(raw)
            cmd = [sys.executable, str(Path(__file__).with_name("two_channel.py")),
                   "--metadata", str(p/"meta.json"), "--trace", str(p/"trace.csv"),
                   "--out", str(p/"out.json")]
            subprocess.run(cmd, check=True, capture_output=True)
            self.assertEqual(json.loads((p/"out.json").read_text())["latency_bracket_ms"], [17,19])
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()

"""R17 synthetic-only analysis tests. All values are invented; no measured display."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from analyze import STUDY, audit


def fixture(*, mode="cross", source="SYNTHETIC"):
    # 0..49 ms every 1 ms; STOP at 15 ms. No human/image/camera.
    rows = ["timestamp_ms,photodiode_signal"]
    for t in range(50):
        if mode == "cross":
            v = 1.0 if t < 23 else 0.0
        elif mode == "rebound":
            v = 1.0 if t < 23 or t >= 29 else 0.0
        elif mode == "censored":
            v = 1.0
        elif mode == "already":
            v = 1.0 if t < 15 else 0.0
        elif mode == "blink":
            v = 0.0 if t in (23,24) else 1.0
        elif mode == "gap":
            if 16 <= t < 37:
                continue
            v = 1.0 if t < 37 else 0.0
        else:
            raise ValueError(mode)
        rows.append(f"{t},{v}")
    raw = ("\n".join(rows)+"\n").encode()
    manifest = {
        "study": STUDY, "source_kind": source,
        "clock_domain": "SINGLE_ACQUISITION_CLOCK",
        "shared_clock_claimed": True, "stop_event_ms": 15.0,
        "active_reference": 1.0, "neutral_reference": 0.0,
        "instrument_reference": "synthetic no-device fixture",
        "display_reference": "synthetic no-monitor fixture",
        "trace_sha256": sha256(raw).hexdigest(),
        "human_participants": 0, "camera_used": False,
        "experimental_images_used": False,
    }
    return manifest, raw


class OpticalAuditTests(unittest.TestCase):
    def test_synthetic_cross_interval_and_nonclaims(self):
        meta, raw = fixture()
        report = audit(meta, raw)
        self.assertEqual(report["state"], "DETECTED_SAMPLE_BRACKET__NOT_CERTIFIED")
        self.assertEqual(report["sample_bracket"]["latency_lower_ms"], 7.0)
        self.assertEqual(report["sample_bracket"]["latency_upper_ms"], 8.0)
        self.assertFalse(report["physical_provenance_verified"])
        self.assertFalse(report["safety_threshold_certified"])
        self.assertFalse(report["human_exposure_authorized"])

    def test_post_confirmation_rebound_is_not_counted_as_success(self):
        meta, raw = fixture(mode="rebound")
        report = audit(meta, raw)
        self.assertEqual(report["state"], "REBOUND_AFTER_NEUTRAL_CONFIRMATION")
        self.assertIsNone(report["sample_bracket"])

    def test_no_transition_is_censored(self):
        meta, raw = fixture(mode="censored")
        result = audit(meta, raw)
        self.assertEqual(result["state"], "RIGHT_CENSORED_NO_CONFIRMED_NEUTRAL")
        self.assertIsNone(result["sample_bracket"])

    def test_already_neutral_is_ambiguous(self):
        meta, raw = fixture(mode="already")
        self.assertEqual(audit(meta, raw)["state"],
                         "AMBIGUOUS_ALREADY_NEUTRAL_AT_FIRST_POST_SAMPLE")

    def test_two_sample_glitch_is_not_confirmed(self):
        meta, raw = fixture(mode="blink")
        self.assertEqual(audit(meta, raw)["state"], "RIGHT_CENSORED_NO_CONFIRMED_NEUTRAL")

    def test_sampling_gap_does_not_become_precise_latency(self):
        meta, raw = fixture(mode="gap")
        self.assertEqual(audit(meta, raw)["state"], "INSUFFICIENT_TIME_RESOLUTION")

    def test_tampering_hash_rejected(self):
        meta, raw = fixture()
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            audit(meta, raw+b"altered")

    def test_no_human_camera_stimulus_or_unshared_clock(self):
        for key,val in (
            ("human_participants", 1),
            ("human_participants", False),
            ("camera_used", True),
            ("experimental_images_used", True),
            ("shared_clock_claimed", False),
            ("clock_domain", "UNSYNCHRONIZED"),
        ):
            m,raw=fixture()
            m[key]=val
            with self.subTest(key=key), self.assertRaises(ValueError):
                audit(m,raw)

    def test_bad_reference_and_clock_rejected(self):
        for key,val in (
            ("stop_event_ms", float("nan")), ("stop_event_ms", True),
            ("stop_event_ms", -1), ("active_reference", 0),
            ("instrument_reference", "x"),
        ):
            m,raw=fixture()
            m[key]=val
            with self.subTest(key=key), self.assertRaises(ValueError):
                audit(m,raw)

    def test_nonmonotonic_and_nonfinite_samples_rejected(self):
        m,raw=fixture()
        for corrupt in (raw+b"1,0\n", raw+b"50,nan\n", raw+b"50,inf\n",
                        raw.replace(b"timestamp_ms,photodiode_signal",b"time,signal")):
            m2=deepcopy(m)
            m2["trace_sha256"]=sha256(corrupt).hexdigest()
            with self.assertRaises(ValueError):
                audit(m2,corrupt)

    def test_missing_baseline_rejected(self):
        m,raw=fixture()
        changed=raw.replace(b"14,1.0",b"14,0.0")
        m["trace_sha256"]=sha256(changed).hexdigest()
        with self.assertRaisesRegex(ValueError,"baseline"):
            audit(m,changed)

    def test_claimed_physical_input_never_auto_verified(self):
        m,raw=fixture(source="DECLARED_PHOTODIODE_CAPTURE")
        result=audit(m,raw)
        self.assertFalse(result["physical_provenance_verified"])
        self.assertIn("DECLARED_ONLY",result["shared_clock"])

    def test_cli_write_once(self):
        m,raw=fixture()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"manifest.json").write_text(json.dumps(m),encoding="utf-8")
            (root/"capture.csv").write_bytes(raw)
            out=root/"report.json"
            args=[sys.executable,str(Path(__file__).with_name("analyze.py")),
                  "--manifest",str(root/"manifest.json"),"--trace",str(root/"capture.csv"),
                  "--out",str(out)]
            subprocess.run(args,check=True,capture_output=True,text=True)
            self.assertFalse(json.loads(out.read_text())["human_exposure_authorized"])
            repeat=subprocess.run(args,capture_output=True,text=True)
            self.assertNotEqual(repeat.returncode,0)


if __name__ == "__main__":
    unittest.main()

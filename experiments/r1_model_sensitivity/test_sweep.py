"""R1 checks: numerical consistency, reproducibility, no eye-response claims.

These tests are not a clinical or optical-bench validation.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from sweep import (
    Case, FIELDS, MODEL_ID, aggregate_error, checked_psf, grid_for,
    make_summary, run_case, write_output,
)


class GridTests(unittest.TestCase):
    def test_preset_sizes_and_nonduplication(self):
        for preset, length in (("smoke", 2), ("pilot", 16), ("extended", 81)):
            with self.subTest(preset=preset):
                grid = grid_for(preset)
                self.assertEqual(len(grid), length)
                self.assertEqual(len(grid), len(set(grid)))
                for case in grid:
                    case.validate()

    def test_deterministic_order(self):
        self.assertEqual(grid_for("pilot"), grid_for("pilot"))

    def test_rejects_out_of_scope(self):
        for case in (
            Case(.1, .27, 4, .45),
            Case(.6, .01, 4, .45),
            Case(.6, .27, 9, .45),
            Case(.6, .27, 4, float("nan")),
        ):
            with self.subTest(case=case), self.assertRaises(ValueError):
                case.validate()
        with self.assertRaises(ValueError):
            grid_for("arbitrary")


class OpticsTests(unittest.TestCase):
    def setUp(self):
        self.case = grid_for("smoke")[0]

    def test_psf_is_nonnegative_normalized_and_symmetric(self):
        p = checked_psf(.45, 520., self.case,
                        n_fft=160, subpixels=3, kernel_size=25)
        self.assertEqual(p.shape, (25, 25))
        self.assertGreaterEqual(p.min(), 0)
        self.assertAlmostEqual(float(p.sum()), 1., places=9)
        self.assertLess(np.max(np.abs(p - p[::-1, ::-1])), 1e-5)

    def test_normalized_joint_error_identity_and_nonnegativity(self):
        p = checked_psf(.45, 520., self.case,
                        n_fft=160, subpixels=3, kernel_size=25)
        q = checked_psf(.25, 520., self.case,
                        n_fft=160, subpixels=3, kernel_size=25)
        self.assertAlmostEqual(aggregate_error({"R": p, "G": p, "B": p},
                                                {"R": p, "G": p, "B": p}), 0.)
        self.assertGreater(aggregate_error({"R": p, "G": p, "B": p},
                                           {"R": q, "G": q, "B": q}), 0.)

    def test_plus_and_minus_are_distinct_model_cases(self):
        rows = run_case(self.case, 1, n_fft=160, subpixels=3, kernel_size=25)
        self.assertEqual({r["direction"] for r in rows},
                         {"plus_delta", "minus_delta"})
        self.assertEqual({r["scope"] for r in rows},
                         {"SIMULATED_PSF_ONLY"})
        self.assertEqual({r["signed_delta_D"] for r in rows}, {+.45, -.45})
        for row in rows:
            for field in ("baseline_error", "shared_error", "channel_error"):
                self.assertTrue(np.isfinite(row[field]))
                self.assertGreaterEqual(row[field], 0)
            for field in FIELDS:
                self.assertIn(field, row)

    def test_outputs_have_required_boundaries_and_manifest(self):
        grid = (self.case,)
        rows = run_case(self.case, 1, n_fft=160, subpixels=3, kernel_size=25)
        summary = make_summary(rows, {"status": "CHECKED"}, grid, preset="unit")
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            write_output(out, grid, rows, summary, preset="unit")
            self.assertEqual(
                {p.name for p in out.iterdir()},
                {"sweep.csv", "summary.json", "manifest.json", "fit_summary.png"},
            )
            with (out / "sweep.csv").open(encoding="utf8", newline="") as f:
                output_rows = list(csv.DictReader(f))
            self.assertEqual(len(output_rows), 2)
            self.assertEqual(output_rows[0]["scope"], "SIMULATED_PSF_ONLY")
            record = json.loads((out / "summary.json").read_text(encoding="utf8"))
            self.assertEqual(record["model_id"], MODEL_ID)
            self.assertEqual(record["human_accommodation_claim"], "NOT_MEASURED")
            self.assertEqual(record["eye_strain_or_clinical_claim"], "NOT_MEASURED")
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf8"))
            self.assertEqual(len(manifest["legacy_model_sha256"]), 64)
            self.assertEqual(len(manifest["runner_sha256"]), 64)
            self.assertEqual(len(manifest["cases"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

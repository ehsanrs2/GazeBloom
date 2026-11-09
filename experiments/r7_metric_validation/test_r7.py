"""R7 tests: predeclared numerical abstention and template-free scan invariants."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from evaluate import (
    FOCUS_GRID_D, PAIR_QUANTIZATION_RMS_PROXY, SIGNIFICANCE_HEURISTIC_SIGMA,
    STUDY, TARGET_RELATIVE_FLOOR, conditioned_alignment, conditioning_gate,
    execute, preference_summary, retinal_focus_curve, target_pair, write_results,
)
from experiments.r3_model_mismatch.evaluate import make_scene
from experiments.r3_model_mismatch.alt_optics import validation_profiles
from experiments.r5_equal_capacity_controls.evaluate import MODELS


class ConditioningGateTests(unittest.TestCase):
    def test_quantization_threshold_fixed_before_observing_pilot(self):
        self.assertAlmostEqual(
            PAIR_QUANTIZATION_RMS_PROXY, np.sqrt(2)/(255*np.sqrt(12)),
            places=15)
        self.assertEqual(SIGNIFICANCE_HEURISTIC_SIGMA, 10.)
        self.assertEqual(TARGET_RELATIVE_FLOOR, .02)
        self.assertGreater(SIGNIFICANCE_HEURISTIC_SIGMA*PAIR_QUANTIZATION_RMS_PROXY,
                           .015)
        self.assertLess(SIGNIFICANCE_HEURISTIC_SIGMA*PAIR_QUANTIZATION_RMS_PROXY,
                        .017)

    def test_identical_near_identical_and_clear_templates(self):
        pair = {-0.45: np.full((3, 6, 6), .4),
                0.45: np.full((3, 6, 6), .4)}
        self.assertFalse(conditioning_gate(pair)["well_conditioned"])
        pair[0.45] = pair[0.45] + .005
        self.assertFalse(conditioning_gate(pair)["well_conditioned"])
        self.assertEqual(conditioning_gate(pair)["quality_flag"],
                         "ABSTAIN_NEAR_DEGENERATE_TARGETS")
        pair[0.45] = pair[-0.45] + .08
        self.assertTrue(conditioning_gate(pair)["well_conditioned"])

    def test_large_historical_score_is_masked_if_near_degenerate(self):
        plus = np.full((3, 4, 4), .5 + 1e-5)
        minus = np.full((3, 4, 4), .5)
        target = {-0.45: minus, 0.45: plus}
        # Predict grossly different images for the tiny target contrast.
        pred = {-0.45: np.zeros_like(plus), 0.45: np.ones_like(plus)}
        scored = conditioned_alignment(pred, target)
        self.assertIsNone(scored["conditioned_A"])
        self.assertGreater(abs(scored["historical_raw_A"]), 100)
        self.assertIsNone(scored["correct_template_count"])

    def test_clear_target_retains_exact_historical_score(self):
        target = {-0.45: np.zeros((3, 4, 4)),
                  0.45: np.full((3, 4, 4), .3)}
        r = conditioned_alignment(target, target)
        self.assertAlmostEqual(r["conditioned_A"], 1., places=12)
        self.assertEqual(r["correct_template_count"], 2)

    def test_malformed_targets_fail_explicitly(self):
        pair = {-0.45: np.ones((3, 4, 4)), 0.45: np.ones((3, 5, 5))}
        with self.assertRaises(ValueError):
            conditioning_gate(pair)
        pair[0.45] = np.ones((3, 4, 4)) * np.nan
        with self.assertRaises(ValueError):
            conditioning_gate(pair)


class FocusProxyTests(unittest.TestCase):
    def test_preference_order_without_any_target_template(self):
        negative = [0., 1., 5., 2., 1., .5, 0.]
        positive = [0., .5, 1., 2., 1., 5., 0.]
        score = preference_summary(negative, positive)
        self.assertAlmostEqual(score["minus_peak_D"], -.25)
        self.assertAlmostEqual(score["plus_peak_D"], .5)
        self.assertAlmostEqual(score["delta_peak_D"], .75)
        self.assertFalse(score["any_boundary_peak"])
        self.assertGreater(score["relative_curve_difference"], 0)

    def test_identical_curves_have_zero_delta_and_zero_difference(self):
        c = [1., 2., 3., 4., 3., 2., 1.]
        r = preference_summary(c, c)
        self.assertEqual(r["delta_peak_D"], 0)
        self.assertEqual(r["relative_curve_difference"], 0)
        self.assertEqual(r["quantity"],
                         "TARGET_FREE_SYNTHETIC_GRADIENT_ENERGY_NOT_ACCOMMODATION")

    def test_nonfinite_and_wrong_grid_rejected(self):
        with self.assertRaises(ValueError):
            preference_summary([0.]*3, [0.]*3)
        with self.assertRaises(ValueError):
            preference_summary([np.nan]*7, [1.]*7)

    def test_alternative_model_curve_finite_and_nonflat_on_texture(self):
        scene = make_scene("original_texture", 64)
        x = np.broadcast_to(scene, (3, 64, 64)).copy()
        curve = retinal_focus_curve(x, validation_profiles()[0])
        self.assertEqual(len(curve), len(FOCUS_GRID_D))
        self.assertTrue(np.isfinite(curve).all())
        self.assertGreater(max(curve) - min(curve), 1e-8)

    def test_shared_psf_target_free_null_same_ideal_luminance(self):
        scene = make_scene("original_texture", 64)
        a = np.broadcast_to(scene, (3, 64, 64)).copy()
        b = a.copy()
        # Weighted luminance is exactly unchanged per pixel.
        b[0] += .025
        b[1] -= .025 * (.2126/.7152)
        pa = validation_profiles()[0]
        x = retinal_focus_curve(a, pa, same_channel_psf=True)
        y = retinal_focus_curve(b, pa, same_channel_psf=True)
        np.testing.assert_allclose(x, y, atol=1e-13, rtol=1e-11)

    def test_all_channel_common_target_is_screening_not_lca_only(self):
        profile = validation_profiles()[0]
        scene = make_scene("original_texture", 64)
        a = target_pair(scene, profile, same_channel_psf=True)
        s = conditioning_gate(a)
        self.assertIsInstance(s["quality_flag"], str)
        self.assertEqual(set(a), {-.45, .45})


class FullMiniPilot(unittest.TestCase):
    def test_single_profile_run_and_artifacts_nonclinical(self):
        rows, summary = execute(
            scenes=("original_texture",),
            profiles=(validation_profiles()[0],),
            size=64, maxiter=90)
        self.assertEqual(len(rows), 1)
        self.assertEqual(summary["study"], STUDY)
        self.assertEqual(summary["rows"], 1)
        self.assertTrue(summary["all_optimizer_success"])
        self.assertTrue(summary["target_gate"]["heuristic_not_calibrated"])
        self.assertEqual(summary["human_accommodation"], "NOT_MEASURED")
        self.assertEqual(summary["clinical_claim"], "NONE")
        self.assertIn(rows[0]["target_gate"], {
            "ABSTAIN_NEAR_DEGENERATE_TARGETS", "USABLE_IN_SIMULATION_ONLY"})
        for name in MODELS:
            key = f"{name}_focus_curve_relative_difference"
            self.assertTrue(np.isfinite(rows[0][key]))
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            write_results(out, rows, summary)
            self.assertEqual(set(x.name for x in out.iterdir()),
                             {"r7_metrics.csv", "summary.json", "manifest.json"})
            data = json.loads((out/"manifest.json").read_text())
            self.assertEqual(len(data["code_sha256"]), 5)
            self.assertTrue(all(len(s)==64 for s in data["code_sha256"].values()))

    def test_invalid_scope_rejected(self):
        with self.assertRaises(ValueError):
            execute(scenes=())
        with self.assertRaises(ValueError):
            execute(size=51)
        with self.assertRaises(ValueError):
            execute(maxiter=0)
        with self.assertRaises(ValueError):
            execute(profiles=())


if __name__=="__main__":
    unittest.main()

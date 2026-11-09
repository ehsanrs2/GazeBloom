"""R5 equal-variable 3HW control tests; no claims about eye response."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from evaluate import (
    CONTROLS, LAMBDA_CHROMA, LAMBDA_DEVIATION, MODELS, SIGNS, STUDY,
    execute, fit_candidates, surrogate_operator, write_outputs,
)
from directional_metric import artifact_proxy
from experiments.r3_model_mismatch.evaluate import make_scene
from alt_optics import validation_profiles


class NullConstructionTests(unittest.TestCase):
    def test_forward_operators_preserve_rgb_field_capacity(self):
        raw = np.random.default_rng(7).normal(size=(3, 8, 5)) + (
            1j * np.random.default_rng(8).normal(size=(3, 8, 5)))
        good = surrogate_operator(raw, "mapped_rgb")
        wrong = surrogate_operator(raw, "permuted_fit_rgb")
        achrom = surrogate_operator(raw, "achromatic_fit_rgb")
        for arr in (good, wrong, achrom):
            self.assertEqual(arr.shape, raw.shape)
            self.assertTrue(np.isfinite(arr).all())
        np.testing.assert_array_equal(good, raw)
        np.testing.assert_array_equal(wrong[0], raw[2])
        np.testing.assert_array_equal(wrong[1], raw[1])
        np.testing.assert_array_equal(wrong[2], raw[0])
        np.testing.assert_allclose(achrom[0], raw.mean(axis=0))
        np.testing.assert_allclose(achrom[0], achrom[1])
        with self.assertRaises(ValueError):
            surrogate_operator(raw, "invalid_null")
        with self.assertRaises(ValueError):
            surrogate_operator(raw[:2], "mapped_rgb")

    def test_chroma_proxy_zero_for_achromatic_and_rejects_nonfinite(self):
        scene = make_scene("original_texture", 64)
        achrom = np.broadcast_to(scene, (3, 64, 64))
        self.assertLess(artifact_proxy(achrom), 1e-14)
        rgb = np.array(achrom, copy=True)
        rgb[0] += .05
        self.assertGreater(artifact_proxy(rgb), 0.0)
        rgb[0, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            artifact_proxy(rgb)


class TargetParityTests(unittest.TestCase):
    def test_all_equal_capacity_arms_receive_exact_same_target_and_regularizers(self):
        scene = make_scene("original_texture", 64)
        calls = []

        def fake_optimize(operator, target, source, *, shared=False,
                          lambda_deviation=.002, lambda_chroma=.01, maxiter=90):
            calls.append({
                "target": target.copy(), "source": source.copy(),
                "op": operator.copy(), "shared": shared,
                "lambda_d": lambda_deviation, "lambda_c": lambda_chroma,
                "maxiter": maxiter,
            })
            arr = np.broadcast_to(source, ((1 if shared else 3),) + source.shape).copy()
            return np.broadcast_to(arr, (3,) + source.shape).copy(), {
                "optimizer_success": True, "iterations": 1, "objective": 0.0,
            }

        with patch("evaluate.optimize_display", side_effect=fake_optimize):
            images, status = fit_candidates(scene, maxiter=9)
        self.assertEqual(len(status), 8)
        self.assertEqual(len(calls), 8)
        self.assertEqual({x["variables"] for x in status if x["arm"] in MODELS},
                         {3 * 64 * 64})
        self.assertEqual({x["variables"] for x in status if x["arm"] == "optimized_gray"},
                         {64 * 64})
        for idx in (0, 4):
            candidate_calls = calls[idx:idx+3]
            for entry in candidate_calls[1:]:
                np.testing.assert_array_equal(candidate_calls[0]["target"], entry["target"])
                np.testing.assert_array_equal(candidate_calls[0]["source"], entry["source"])
            for entry in candidate_calls:
                self.assertFalse(entry["shared"])
                self.assertEqual(entry["lambda_d"], LAMBDA_DEVIATION)
                self.assertEqual(entry["lambda_c"], LAMBDA_CHROMA)
                self.assertEqual(entry["maxiter"], 9)
        self.assertEqual(set(images), set(CONTROLS))
        self.assertEqual(set(images["mapped_rgb"]), set(SIGNS))

    def test_real_optimizers_independently_fit_different_rgb_solutions(self):
        scene = make_scene("original_texture", 64)
        images, statuses = fit_candidates(scene, maxiter=90)
        self.assertEqual(len(statuses), 8)
        self.assertTrue(all(s["success"] for s in statuses))
        for name in MODELS:
            for sign in SIGNS:
                arr = images[name][sign]
                self.assertEqual(arr.shape, (3, 64, 64))
                self.assertGreaterEqual(arr.min(), -1e-12)
                self.assertLessEqual(arr.max(), 1 + 1e-12)
        for sign in SIGNS:
            # Independently fitted controls cannot be the simple RB swap
            # of the original solution, nor identically the mapped solution.
            original = images["mapped_rgb"][sign]
            swapped_fit = images["permuted_fit_rgb"][sign]
            avg_fit = images["achromatic_fit_rgb"][sign]
            self.assertGreater(np.linalg.norm(original - swapped_fit), .001)
            self.assertGreater(np.linalg.norm(original - avg_fit), .001)


class PilotOutputTests(unittest.TestCase):
    def test_small_scope_completes_and_outputs_explicit_unknowns(self):
        rows, summary = execute(
            size=64, maxiter=90, scenes=("original_texture",),
            profiles=(validation_profiles()[0],),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(summary["study"], STUDY)
        self.assertEqual(summary["paired_directional_rows"], 1)
        self.assertEqual(summary["result_scope"],
                         "SIMULATOR_ONLY_NO_EYE_OR_SCREEN_MEASUREMENT")
        self.assertTrue(summary["all_optimizers_converged"])
        self.assertEqual(summary["invariants"]["same_RGB_free_variable_count"], True)
        self.assertEqual(summary["invariants"]["nulls_independently_refit"], True)
        for name in ("mapped_alignment", "permuted_fit_alignment",
                     "achromatic_fit_alignment", "mapped_l2",
                     "permuted_fit_l2", "achromatic_fit_l2"):
            self.assertTrue(np.isfinite(rows[0][name]))
        with tempfile.TemporaryDirectory() as path:
            out = Path(path)
            write_outputs(out, rows, summary)
            self.assertEqual({x.name for x in out.iterdir()},
                             {"equal_capacity.csv", "summary.json", "manifest.json"})
            info = json.loads((out / "manifest.json").read_text())
            self.assertEqual(len(info["sha256"]), 5)
            self.assertTrue(all(len(x) == 64 for x in info["sha256"].values()))
            self.assertFalse(info["human_data"])
            self.assertFalse(info["optical_instrument_data"])

    def test_invalid_training_dimensions_and_empty_scope(self):
        with self.assertRaises(ValueError):
            fit_candidates(np.ones((50, 49)))
        with self.assertRaises(ValueError):
            fit_candidates(np.ones((64, 64)), maxiter=0)
        with self.assertRaises(ValueError):
            execute(scenes=())
        with self.assertRaises(ValueError):
            execute(profiles=())


if __name__ == "__main__":
    unittest.main()

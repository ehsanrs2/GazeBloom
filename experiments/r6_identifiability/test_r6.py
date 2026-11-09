"""R6: falsification, nonclinical and independent-target test invariants."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from evaluate import (
    CHROMA_CAP, MODELS, SIGNS, STUDY, TARGET_GENERATOR,
    chromatic_deviation, cross_generated_fit, linear_luminance,
    match_scene_pair, matching_limit, run, score_pair, write_results,
)
from experiments.r3_model_mismatch.evaluate import make_scene
from alt_optics import validation_profiles, optics_otfs, optical_forward
from inverse import optical_otfs, forward


def gen_profile():
    return next(p for p in validation_profiles() if p.name == TARGET_GENERATOR)


class BudgetInvariants(unittest.TestCase):
    def test_weighted_luminance_not_simple_rgb_average(self):
        x = np.zeros((3, 4, 4))
        x[1] = .8
        self.assertAlmostEqual(linear_luminance(x)[0, 0], .7152 * .8)
        self.assertGreater(linear_luminance(x)[0, 0], x.mean(axis=0)[0, 0])
        np.testing.assert_allclose(
            np.einsum("c,chw->hw", np.array((.2126, .7152, .0722)),
                      chromatic_deviation(x)), 0, atol=1e-14)

    def test_six_independent_rgb_fields_match_luminance_and_chroma(self):
        scene = make_scene("original_texture", 64)
        rng = np.random.default_rng(19)
        inputs = {k: {} for k in MODELS}
        for name in MODELS:
            for sign in SIGNS:
                # bounded but distinct RGB candidates with nonzero chroma.
                inputs[name][sign] = np.clip(
                    scene[None] + rng.normal(0, .07, size=(3, 64, 64)), 0, 1
                )
        originals = {name: {s: x.copy() for s, x in v.items()}
                     for name, v in inputs.items()}
        matched, stats = match_scene_pair(scene, inputs)
        self.assertGreater(stats["common_chroma_abs"], 0)
        self.assertLessEqual(stats["common_chroma_abs"], CHROMA_CAP)
        for name in MODELS:
            for sign in SIGNS:
                out = matched[name][sign]
                self.assertGreaterEqual(out.min(), -1e-10)
                self.assertLessEqual(out.max(), 1 + 1e-10)
                np.testing.assert_allclose(linear_luminance(out), scene, atol=2e-14)
                self.assertAlmostEqual(
                    float(np.mean(np.abs(chromatic_deviation(out)))),
                    stats["common_chroma_abs"], places=13
                )
                np.testing.assert_array_equal(inputs[name][sign], originals[name][sign])

    def test_budget_limit_rejects_invalid_and_empty_chroma(self):
        scene = make_scene("original_texture", 64)
        constant = np.broadcast_to(scene, (3, 64, 64))
        limit, energy = matching_limit(constant, scene)
        self.assertGreaterEqual(limit, 0)
        self.assertAlmostEqual(energy, 0, places=14)
        data = {name: {s: constant.copy() for s in SIGNS} for name in MODELS}
        with self.assertRaisesRegex(ValueError, "matching unavailable"):
            match_scene_pair(scene, data)
        with self.assertRaises(ValueError):
            matching_limit(constant, np.full((64, 64), -1.))


class CrossModelTargetTests(unittest.TestCase):
    def test_all_arms_see_same_non_nominal_target_for_each_sign(self):
        scene = make_scene("original_texture", 64)
        captured = []

        def fake_solver(operator, target, source, **kwargs):
            captured.append((operator.copy(), target.copy(), source.copy(), kwargs))
            field = np.broadcast_to(source, (3,) + source.shape).copy()
            return field, {"optimizer_success": True, "iterations": 0}

        with patch("evaluate.optimize_display", side_effect=fake_solver):
            _, statuses = cross_generated_fit(scene, generator=gen_profile(), maxiter=10)
        self.assertEqual(len(captured), 6)
        self.assertEqual({s["free_parameters"] for s in statuses}, {3*64*64})
        self.assertTrue(all(not s["nominal_R2_target_used"] for s in statuses))
        for i in (0, 3):
            for j in (i+1, i+2):
                np.testing.assert_array_equal(captured[i][1], captured[j][1])
                np.testing.assert_array_equal(captured[i][2], captured[j][2])
                self.assertEqual(captured[i][3], captured[j][3])
        src = np.broadcast_to(scene, (3, 64, 64))
        nominal_otfs, nominal_target_otfs = optical_otfs(4, SIGNS[0], size=64)
        nominal_target = forward(src, nominal_target_otfs)
        alt_target = captured[0][1]
        self.assertGreater(float(np.linalg.norm(alt_target - nominal_target)), 1e-5)

    def test_target_generator_not_scored_as_holdout(self):
        with self.assertRaises(ValueError):
            run(scenes=("original_texture",), profiles=(gen_profile(),),
                generator=gen_profile())


class PilotSmokeTests(unittest.TestCase):
    def test_one_heldout_profile_runs_and_preserves_explicit_scope(self):
        profile = validation_profiles()[0]
        rows, summary = run(scenes=("original_texture",),
                            profiles=(profile,), generator=gen_profile(),
                            size=64, maxiter=90)
        self.assertEqual(len(rows), 1)
        self.assertEqual(summary["rows"], 1)
        self.assertEqual(summary["study"], STUDY)
        self.assertEqual(summary["directional_defined_rows"], 1)
        self.assertEqual(summary["all_optimizer_success"], True)
        self.assertEqual(summary["target_generator"]["name"], TARGET_GENERATOR)
        self.assertEqual(summary["claims"]["human_accommodation"], "NOT_MEASURED")
        self.assertEqual(rows[0]["scope"], "SYNTHETIC_CROSS_TARGET_AND_PROXY_MATCHING_ONLY")
        self.assertLessEqual(rows[0]["max_luminance_mismatch"], 1e-10)
        for name in ("matched_mapped_A", "matched_permuted_A", "matched_achromatic_A"):
            self.assertTrue(np.isfinite(rows[0][name]))
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            write_results(directory, rows, summary)
            self.assertEqual({p.name for p in directory.iterdir()},
                             {"identifiability.csv", "summary.json", "manifest.json"})
            manifest = json.loads((directory / "manifest.json").read_text())
            self.assertEqual(len(manifest["source_sha256"]), 6)
            self.assertTrue(all(len(s) == 64 for s in manifest["source_sha256"].values()))

    def test_bad_inputs_rejected(self):
        for kwargs in ({"size": 51}, {"maxiter": 0}, {"scenes": ()},
                       {"profiles": ()}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                run(**kwargs)


if __name__ == "__main__":
    unittest.main()

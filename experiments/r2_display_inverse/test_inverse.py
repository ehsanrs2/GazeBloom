"""R2 deterministic checks; NOT a test of actual ocular accommodation."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.optimize._numdiff import approx_derivative
from inverse import (MODEL, encode_decode_8bit, evaluate, forward,
                     objective, optimize_display, psf_otf,
                     retinal_relative_error, scene_pattern, write_results)


class InverseTests(unittest.TestCase):
    def test_scene_reproducible_and_gamut(self):
        a = scene_pattern(32)
        self.assertTrue(np.array_equal(a, scene_pattern(32)))
        self.assertTrue(np.all((a >= 0) & (a <= 1)))
        with self.assertRaises(ValueError):
            scene_pattern(31)

    def test_psf_to_otf_is_centered(self):
        p = np.zeros((3, 3))
        p[1, 1] = 1.
        h = np.stack([psf_otf(p, (8, 8))] * 3)
        x = np.random.default_rng(42).random((3, 8, 8))
        np.testing.assert_allclose(forward(x, h), x, atol=1e-12)
        self.assertLess(retinal_relative_error(x, x), 1e-12)

    def test_blur_preserves_constant_intensity(self):
        p = np.array([[0.0, .125, 0.0], [.125, .5, .125], [0.0, .125, 0.0]])
        h = np.stack([psf_otf(p, (8, 8))] * 3)
        x = np.full((3, 8, 8), .45)
        np.testing.assert_allclose(forward(x, h), x, atol=1e-12)

    def test_gradient_matches_finite_difference_rgb_and_shared(self):
        p = np.array([[0.0, .1, 0.0], [.1, .6, .1], [0.0, .1, 0.0]])
        h = np.stack([psf_otf(p, (4, 4))] * 3)
        source = np.random.default_rng(13).uniform(.2, .8, size=(4, 4))
        target = np.random.default_rng(9).uniform(.2, .8, size=(3, 4, 4))
        for shared in (True, False):
            with self.subTest(shared=shared):
                a = np.random.default_rng(17).uniform(.25, .75, (1 if shared else 3, 4, 4)).ravel()
                fun = lambda v: objective(v, h, target, source,
                                         shared=shared, lambda_deviation=.002,
                                         lambda_chroma=.01)
                derivative = approx_derivative(lambda v: fun(v)[0], a, method='3-point')
                np.testing.assert_allclose(fun(a)[1], derivative, atol=2e-8, rtol=2e-5)

    def test_shared_optimization_is_not_worse_than_source(self):
        p = np.zeros((3, 3))
        p[1, 1] = 1
        h = np.stack([psf_otf(p, (32, 32))] * 3)
        source = scene_pattern(32)
        t = np.repeat(source[None], 3, axis=0)
        rgb, status = optimize_display(h, t, source, maxiter=10)
        self.assertTrue(np.isfinite(rgb).all())
        self.assertGreaterEqual(rgb.min(), 0.)
        self.assertLessEqual(rgb.max(), 1.)
        np.testing.assert_allclose(rgb, t, atol=1e-7)
        self.assertTrue(status['optimizer_success'])

    def test_gamma_8bit_roundtrip_bounded(self):
        x = np.linspace(0, 1, 123).reshape((3, 41))
        y = encode_decode_8bit(x)
        self.assertTrue(np.isfinite(y).all())
        self.assertGreaterEqual(y.min(), 0.)
        self.assertLessEqual(y.max(), 1.)
        self.assertLess(np.max(np.abs(x-y)), .009)
        with self.assertRaises(ValueError):
            encode_decode_8bit(x, encode_gamma=0)

    def test_full_model_nominal_and_holdout(self):
        data, images = evaluate(pupil_mm=4, delta_D=.45, n=64, maxiter=75)
        self.assertEqual(data['model'], MODEL)
        self.assertEqual(data['scope'], 'COMPUTATIONAL_ONLY_NOT_EYE_MEASUREMENT')
        self.assertEqual(data['physiology'], 'NOT_MEASURED')
        self.assertIn('3.5', data['holdout_pupil_errors'])
        self.assertIn('4.5', data['holdout_pupil_errors'])
        self.assertTrue(data['optimizer']['rgb']['optimizer_success'])
        self.assertTrue(data['optimizer']['shared']['optimizer_success'])
        # In-model, same-stimulus case: checked as a regression, not a physical guarantee.
        self.assertLess(data['metrics']['rgb']['retinal_image_rel_l2'],
                        data['metrics']['shared']['retinal_image_rel_l2'])
        self.assertLess(data['metrics']['shared']['retinal_image_rel_l2'],
                        data['metrics']['unmodified']['retinal_image_rel_l2'])
        for label in ('shared', 'rgb'):
            self.assertTrue(np.all((images[label] >= 0) & (images[label] <= 1)))
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            write_results(out, data, images)
            self.assertEqual(set(x.name for x in out.iterdir()),
                             {'summary.json', 'arrays.npz', 'comparison.png', 'manifest.json'})
            stored = json.loads((out / 'summary.json').read_text())
            self.assertEqual(stored['physiology'], 'NOT_MEASURED')


if __name__ == '__main__':
    unittest.main()

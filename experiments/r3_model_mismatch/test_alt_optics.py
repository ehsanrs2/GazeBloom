"""R3 alternate-model numerical invariants, not human-eye validation."""
from __future__ import annotations

import math
import unittest

import numpy as np

from alt_optics import (
    ForwardProfile, centered_otf, chromatic_focus_D, code_to_light,
    mix_channels, optical_forward, scalar_psf, spectral_psf,
    validation_profiles,
)
from evaluate import FROZEN_DELTAS, FROZEN_SCENES, make_scene


class R3PhysicsSurrogateTests(unittest.TestCase):
    def test_frozen_experiment_definitions(self):
        self.assertEqual(FROZEN_DELTAS, (-.45, .45))
        self.assertEqual(len(FROZEN_SCENES), 2)
        self.assertEqual(len(validation_profiles()), 6)
        self.assertEqual(len(set(x.name for x in validation_profiles())), 6)

    def test_profile_finite_bounds(self):
        for override in ({"gamma_actual": float("nan")},
                         {"channel_leakage": .99},
                         {"pupil_mm": 0.},
                         {"spectral_halfwidth_nm": 999.}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                ForwardProfile("bad", **override)

    def test_psf_is_nonnegative_normalized_and_angular_sampled(self):
        p = scalar_psf(chromatic_focus_D(520.), 520.,
                       pupil_mm=4., n_fft=192, kernel_size=17,
                       subpixels=2)
        self.assertEqual(p.shape, (17, 17))
        self.assertGreaterEqual(p.min(), 0)
        self.assertAlmostEqual(float(p.sum()), 1., places=12)
        self.assertTrue(np.isfinite(p).all())

    def test_alternative_spectrum_differs_from_single_wavelength(self):
        mono = ForwardProfile("mono", spectral_halfwidth_nm=0)
        broad = ForwardProfile("broad", spectral_halfwidth_nm=18)
        a = spectral_psf(520., .45, mono, n_fft=192,
                         kernel_size=17, subpixels=2)
        b = spectral_psf(520., .45, broad, n_fft=192,
                         kernel_size=17, subpixels=2)
        self.assertAlmostEqual(float(b.sum()), 1., places=10)
        self.assertGreater(float(np.linalg.norm(a - b)), 1e-6)

    def test_synthetic_aberration_changes_psf(self):
        p = scalar_psf(.45, 520., pupil_mm=4., n_fft=192,
                       kernel_size=17, subpixels=2)
        q = scalar_psf(.45, 520., pupil_mm=4., n_fft=192,
                       kernel_size=17, subpixels=2, astig_opd_um=.15)
        self.assertGreater(float(np.linalg.norm(p - q)), 1e-5)

    def test_own_fourier_convolution_identity(self):
        kernel = np.zeros((3, 3))
        kernel[1, 1] = 1.
        h = np.stack([centered_otf(kernel, (8, 8))] * 3)
        source = np.random.default_rng(77).random((3, 8, 8))
        np.testing.assert_allclose(optical_forward(source, h), source,
                                   atol=1e-12)

    def test_constant_energy_through_psf(self):
        kernel = np.array([[0, .125, 0], [.125, .5, .125], [0, .125, 0]])
        h = np.stack([centered_otf(kernel, (8, 8))] * 3)
        source = np.ones((3, 8, 8)) * .5
        np.testing.assert_allclose(optical_forward(source, h), source,
                                   atol=1e-12)

    def test_coding_and_channel_mix_are_bounded(self):
        x = np.random.default_rng(2).uniform(.1, .9, (3, 8, 8))
        y = code_to_light(x, gamma_actual=2.4)
        self.assertTrue(np.all((0 <= y) & (y <= 1)))
        self.assertGreater(float(np.max(np.abs(y - x))), .001)
        mixed = mix_channels(x, .09)
        np.testing.assert_allclose(mixed.sum(axis=0), x.sum(axis=0),
                                   atol=1e-12)
        np.testing.assert_allclose(mix_channels(x, 0), x, atol=1e-12)
        with self.assertRaises(ValueError):
            code_to_light(np.ones_like(x) * 1.5, gamma_actual=2.2)

    def test_scenes_differ_and_within_gamut(self):
        a = make_scene(FROZEN_SCENES[0], 64)
        b = make_scene(FROZEN_SCENES[1], 64)
        self.assertEqual(a.shape, (64, 64))
        self.assertEqual(b.shape, (64, 64))
        self.assertGreater(float(np.linalg.norm(a-b)), 1.)
        for x in (a, b):
            self.assertGreaterEqual(x.min(), 0)
            self.assertLessEqual(x.max(), 1)

    def test_psf_sampling_resolution_is_descriptive_only(self):
        p = scalar_psf(.2, 617, pupil_mm=4., n_fft=192,
                       kernel_size=17, subpixels=2)
        q = scalar_psf(.2, 617, pupil_mm=4., n_fft=256,
                       kernel_size=17, subpixels=2)
        discrepancy = float(np.linalg.norm(p-q) / np.linalg.norm(q))
        self.assertTrue(math.isfinite(discrepancy))
        self.assertLess(discrepancy, .2)  # broad sanity bound, not validity gate


if __name__ == "__main__":
    unittest.main()

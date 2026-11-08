"""Alternative (not empirically validated) forward optics for R3 stress testing.

This implementation does not call the R1/R2 monochromatic PSF generator.
It uses an independently written scalar pupil FFT, finite-width synthetic
primary spectra, toy Zernike-like phase terms, and a channel-mixing proxy.
It is still a *simulation* in the same broad family of diffraction models;
it is NOT independent physical or human-eye validation.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import isfinite, pi

import numpy as np
from scipy.ndimage import map_coordinates

RGB_PEAKS_NM = (617., 520., 449.)
CHANNELS = ("R", "G", "B")


@dataclass(frozen=True)
class ForwardProfile:
    name: str
    pupil_mm: float = 4.
    spectral_halfwidth_nm: float = 0.
    astig_opd_um: float = 0.
    coma_opd_um: float = 0.
    gamma_actual: float = 2.2
    channel_leakage: float = 0.

    def __post_init__(self):
        if not (2 <= self.pupil_mm <= 6.5 and
                0 <= self.spectral_halfwidth_nm <= 35 and
                0 <= self.astig_opd_um <= .3 and
                0 <= self.coma_opd_um <= .3 and
                1.6 <= self.gamma_actual <= 2.8 and
                0 <= self.channel_leakage <= .15):
            raise ValueError("outside R3 exploratory input bounds")
        if not all(isfinite(v) for v in (
            self.pupil_mm, self.spectral_halfwidth_nm,
            self.astig_opd_um, self.coma_opd_um,
            self.gamma_actual, self.channel_leakage,
        )):
            raise ValueError("profile parameters must be finite")


def chromatic_focus_D(wavelength_nm: float) -> float:
    """Same published LCA relation as R2; shared assumption explicitly documented."""
    return 2.071 - 633.46 / (wavelength_nm - 214.10)


def scalar_psf(
    defocus_D: float, wavelength_nm: float, *,
    pupil_mm: float, astig_opd_um: float = 0.,
    coma_opd_um: float = 0., n_fft: int = 384,
    extent_mm: float = 8., kernel_size: int = 49,
    subpixels: int = 3, distance_m: float = .6, pitch_mm: float = .27,
) -> np.ndarray:
    """Circular pupil with defocus + synthetic astig/coma, image-space sampling.

    Aberration terms are illustrative OPD coefficients, **not** measured
    Zernike RMS coefficients of an actual eye. Output PSF integrates to one.
    """
    if not (n_fft >= 128 and n_fft % 2 == 0 and kernel_size % 2 and
            kernel_size >= 3 and subpixels >= 1 and
            extent_mm > pupil_mm * 1.25 and
            400 <= wavelength_nm <= 700 and
            .3 <= distance_m <= 1.5 and .12 <= pitch_mm <= .6):
        raise ValueError("invalid scalar diffraction grid")
    if not all(isfinite(x) for x in (
        defocus_D, wavelength_nm, pupil_mm, astig_opd_um, coma_opd_um,
        distance_m, pitch_mm
    )):
        raise ValueError("nonfinite optics input")
    lam = wavelength_nm * 1e-9
    extent_m = extent_mm * 1e-3
    dx = extent_m / n_fft
    axis = (np.arange(n_fft, dtype=np.float64) - n_fft / 2) * dx
    yy, xx = np.meshgrid(axis, axis, indexing="ij")
    radius_m = pupil_mm * 0.5e-3
    rho2 = (xx * xx + yy * yy) / radius_m**2
    aperture = rho2 <= 1.
    # OPD of a thin-lens defocus, plus Zernike-like uncalibrated perturbations.
    wavefront_m = (
        defocus_D * (xx * xx + yy * yy) * .5
        + astig_opd_um * 1e-6 * (xx * xx - yy * yy) / radius_m**2
        + coma_opd_um * 1e-6 * (
            3. * (xx * xx + yy * yy) / radius_m**2 - 2.
        ) * (xx / radius_m)
    )
    phasor = aperture * np.exp(2j * pi * wavefront_m / lam)
    field = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(phasor)))
    irradiance = np.abs(field)**2
    angle_step = lam / extent_m
    angle_per_pixel = pitch_mm * 1e-3 / distance_m
    offsets = (np.arange(subpixels) + .5) / subpixels - .5
    coord = (
        np.arange(-(kernel_size // 2), kernel_size // 2 + 1)[:, None]
        + offsets[None, :]
    ).reshape(-1)
    index = n_fft / 2 + coord * angle_per_pixel / angle_step
    iy, ix = np.meshgrid(index, index, indexing="ij")
    sampled = map_coordinates(
        irradiance, [iy, ix], order=1, mode="constant",
        cval=0., prefilter=False
    )
    integral = sampled.reshape(
        kernel_size, subpixels, kernel_size, subpixels
    ).mean(axis=(1, 3))
    integral = np.maximum(integral, 0.)
    total = float(integral.sum())
    if not isfinite(total) or total <= 0:
        raise ValueError("invalid PSF power")
    return integral / total


def spectral_psf(
    peak_nm: float, additional_defocus_D: float, profile: ForwardProfile,
    *, n_fft: int = 384, kernel_size: int = 49,
    subpixels: int = 3,
) -> np.ndarray:
    """Unmeasured 3-sample primary: fixed normalized weights .25/.50/.25."""
    half = profile.spectral_halfwidth_nm
    samples = ((peak_nm, 1.),) if half == 0 else (
        (peak_nm - half, .25), (peak_nm, .50), (peak_nm + half, .25)
    )
    out = np.zeros((kernel_size, kernel_size), dtype=np.float64)
    for wavelength, weight in samples:
        focus = chromatic_focus_D(wavelength) + additional_defocus_D
        out += weight * scalar_psf(
            focus, wavelength, pupil_mm=profile.pupil_mm,
            astig_opd_um=profile.astig_opd_um,
            coma_opd_um=profile.coma_opd_um, n_fft=n_fft,
            kernel_size=kernel_size, subpixels=subpixels
        )
    if not np.isclose(out.sum(), 1., atol=1e-10):
        raise AssertionError("spectral weights did not normalize")
    return out


def centered_otf(psf: np.ndarray, image_shape: tuple[int, int]) -> np.ndarray:
    """Separate implementation of centered circular PSF convolution."""
    kh, kw = psf.shape
    if kh % 2 == 0 or kw % 2 == 0 or kh > image_shape[0] or kw > image_shape[1]:
        raise ValueError("kernel must be odd-sized and fit image")
    zero = np.zeros(image_shape)
    zero[:kh, :kw] = psf
    zero = np.roll(zero, (-kh // 2 + 1, -kw // 2 + 1), axis=(0, 1))
    return np.fft.rfft2(zero)


@lru_cache(maxsize=80)
def optics_otfs(profile: ForwardProfile, delta_D: float,
                size: int = 64) -> tuple[np.ndarray, np.ndarray]:
    if size < 49:
        raise ValueError("R3 requires image >= PSF kernel")
    baseline = []
    target = []
    for peak in RGB_PEAKS_NM:
        baseline.append(centered_otf(spectral_psf(peak, 0., profile), (size, size)))
        target.append(centered_otf(spectral_psf(peak, delta_D, profile), (size, size)))
    return np.stack(baseline), np.stack(target)


def optical_forward(image: np.ndarray, otfs: np.ndarray) -> np.ndarray:
    if image.ndim != 3 or image.shape[0] != 3 or image.shape != (3, otfs.shape[1], (otfs.shape[2] - 1) * 2):
        raise ValueError("R3 expects (3,N,N) with even N")
    return np.fft.irfft2(
        np.fft.rfft2(image, axes=(-2, -1)) * otfs,
        s=image.shape[-2:], axes=(-2, -1)
    )


def mix_channels(arr: np.ndarray, leakage: float) -> np.ndarray:
    """Toy cross-channel mixing, not cone spectral sensitivities."""
    return (1. - leakage) * arr + leakage * arr.mean(axis=0, keepdims=True)


def code_to_light(image: np.ndarray, gamma_actual: float, encoded_gamma: float = 2.2) -> np.ndarray:
    """Approximate coding with 8-bit roundtrip; NOT sRGB EOTF or a measured display."""
    if not np.isfinite(image).all() or image.min() < -1e-9 or image.max() > 1 + 1e-9:
        raise ValueError("input RGB outside ideal [0,1]")
    digital = np.rint(255. * np.clip(image, 0., 1.) ** (1. / encoded_gamma)) / 255.
    return digital ** gamma_actual


def relative_l2(pred: np.ndarray, target: np.ndarray) -> float:
    return float(np.linalg.norm(pred - target) / max(np.linalg.norm(target), 1e-12))


def validation_profiles() -> tuple[ForwardProfile, ...]:
    """FROZEN A PRIORI synthetic mismatches. Not samples of real display/eye."""
    return (
        ForwardProfile("alt_monochrome"),
        ForwardProfile("spectral_3sample", spectral_halfwidth_nm=18.),
        ForwardProfile("spectral_aberrated", spectral_halfwidth_nm=18.,
                       astig_opd_um=.10, coma_opd_um=.05),
        ForwardProfile("spectral_aberrated_gamma24", spectral_halfwidth_nm=18.,
                       astig_opd_um=.10, coma_opd_um=.05, gamma_actual=2.4),
        ForwardProfile("spectral_aberrated_pupil45", pupil_mm=4.5,
                       spectral_halfwidth_nm=18., astig_opd_um=.10,
                       coma_opd_um=.05),
        ForwardProfile("spectral_aberrated_leakage", spectral_halfwidth_nm=18.,
                       astig_opd_um=.10, coma_opd_um=.05, channel_leakage=.06),
    )

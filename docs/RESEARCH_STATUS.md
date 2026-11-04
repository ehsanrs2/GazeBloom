# GazeBloom — Research status (2026-11-04)

Goal: investigate whether image-only stimuli on a fixed-distance ordinary monitor can influence *objective* ocular accommodation, and eventually whether an eye-break application helps people working at monitors.

| Question | Evidence | Status |
| --- | --- | --- |
| Q1: modeled retinal target can be achieved by a screen stimulus? | Approximate Gaussian/LCA pilot and scalar wave-optics PSF optimization | **Unresolved**: large residual error |
| Q2: objectively measured accommodation changes in response? | Analysis script tested on **synthetic data only** | **Not studied in humans** |
| Q3: reduces digital eye strain compared with matched breaks? | None | **Not studied** |

## Model assumptions
Nominal fixed screen distance 0.60 m, pixel pitch 0.27 mm, pupil 4 mm; assumed red, green, blue peak wavelengths 617, 520, 449 nm (not measured spectra); hypothetical defocus targets ±0.45 D. The simplified model omits individual ocular aberrations, pupil dynamics, aging, scatter, display spectra and other factors.

## Earlier restricted-simulation result
Per-channel blur was 1.35% (near) and 1.49% (far) better than common-channel blur at a normalized PSF error objective, while substantial error remained. Those are **deterministic model comparisons, not human or medical outcomes**.

## Evidence gates
1. Check model optics, units, gamma and RGB spectral assumptions independently.
2. Replace restricted Gaussian rendering with physically constrained screen image optimization; include achievable intensity, clipping, and colorimetry.
3. Sweep viewing distance, pitch, pupil size, and display spectra; compare with achromatic and unmodified controls.
4. If Q1 is robust, pre-register objective dynamic autorefractor/photorefractor experiments, with expert oversight.
5. Only if Q2 succeeds, test comfort/strain against normal breaks in a controlled study (Q3).

Historical scripts and numerical files are under experiments/ and outputs/. No measured eyes or human subjects were used for current project results.

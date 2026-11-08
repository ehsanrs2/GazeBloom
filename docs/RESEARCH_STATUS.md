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

## R1 stage (research/r1-waveoptics-audit-sensitivity)

Track B is now prioritized; Track A remains available but feature growth is paused.
The R1 code reports normalized model PSF fit error, parameter sensitivity and
descriptive numerical convergence. Its 3-parameter RGB optimizer can be expected
to fit better than the single-parameter shared-RGB baseline, without implying
any real optical or ocular accommodation benefit.

See [R1 protocol](../experiments/r1_model_sensitivity/README_FA.md).

The 16-case / 32-row pilot is complete in CI; full reviewed results: [R1 result review](../experiments/r1_model_sensitivity/RESULTS_REVIEW_FA.md). Median model-only PSF L2 residual **0.7174**, median relative fit gain **2.37%** versus single-sigma shared-RGB blur. Q1 is **not** established; Q2 and Q3 have no human observations.
The original Q1 model's outputs and prior metrics have not been replaced;
the new run generates results into an ignored reproduction directory.
Neither Q2 (human accommodation) nor Q3 (eye strain improvement) is measurable
or established in this stage.

## R2 — bounded-display inversion under review

The new R2 simulator optimizes normalized RGB pixel intensities within [0,1]
for one synthetic image. It compares unmodified source, independently optimized
achromatic display image, and individually optimized R/G/B image, and measures
model-internal relative retinal-image L2 discrepancy. Gamma and pupil perturbation
are exploratory sensitivity checks. This model-based image metric is NOT comparable
to the PSF kernel residuals reported in R1.

Because the target is constructed with the same model used to optimize/evaluate,
this experiment carries **inverse crime** risk and does not establish real-world
optical accuracy. It is not a validated ChromaBlur reproduction or evidence that
ocular accommodation changes. See [R2 protocol](../experiments/r2_display_inverse/README_FA.md).

## Evidence gates
1. Check model optics, units, gamma and RGB spectral assumptions independently.
2. Replace restricted Gaussian rendering with physically constrained screen image optimization; include achievable intensity, clipping, and colorimetry.
3. Sweep viewing distance, pitch, pupil size, and display spectra; compare with achromatic and unmodified controls.
4. If Q1 is robust, pre-register objective dynamic autorefractor/photorefractor experiments, with expert oversight.
5. Only if Q2 succeeds, test comfort/strain against normal breaks in a controlled study (Q3).

Historical scripts and numerical files are under experiments/ and outputs/. No measured eyes or human subjects were used for current project results.

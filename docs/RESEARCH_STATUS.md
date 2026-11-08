# GazeBloom — Research status (2026-11-08)

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

## R3 — alternative synthetic forward-model stress test

Track B R2 is integrated into main as a simulation-only image inverse solver.
R3 evaluates R2-optimized images under a **separately implemented synthetic**
pupil-FFT forward model with toy polychromatic spectra, astigmatism/coma,
gamma uncertainty, and channel mixing. It freezes 2 scenes x 2 signed
defocus cases x 6 evaluator profiles. Passing a cross-simulator stress
test is NOT physical validation, and does NOT measure eye accommodation.

See [R3 protocol](../experiments/r3_model_mismatch/README_FA.md).

The completed R3 experiment reported **24/24 in-model-family synthetic stress comparisons** with lower RGB relative image error than shared-gray, under six frozen alternative profiles. See [R3 results](../experiments/r3_model_mismatch/RESULTS_REVIEW_FA.md). These are *not* independent physical optic measurements and do not establish Q1, Q2 or Q3.

## R4 — in-silico signed color-order control (numerical pilot complete)

The R4 protocol compares paired ±0.45 D **synthetic templates** using an
R2-trained chromatic stimulus and three controls: unchanged gray source,
optimized grayscale source, and RGB with R/B channels swapped. The red/blue
permutation preserves RGB pixel value distribution and channel capacity,
but it is not a separately optimized null. A signed difference-in-differences
template score is **not** a predicted or observed direction of human
accommodation. Evaluation is on the R3 synthetic model family, never
an optical instrument or human subject.

[Protocol (Persian)](../experiments/r4_directional_controls/README_FA.md).

The frozen R4 run completed **12/12** simulated signed-image pairs:
median directional template alignment **+0.6686** (RGB), **−0.6016**
(red/blue channel swap), and **+0.0096** (optimized gray). The swap preserved
per-pixel RGB numeric mean, saturation count, chroma magnitude, and field
capacity but was **not reoptimized independently**. These are *modeled*
retinal template-order comparisons, not actual eye-response directions.
[Reviewed results](../experiments/r4_directional_controls/RESULTS_REVIEW_FA.md).

## R5 — independent same-parameter RGB training nulls (numerical pilot complete)

This stage independently reoptimizes three **3HW RGB** pixel fields for
the exact same nominal R2 synthetic target under identical initial values,
regularizers, RGB bounds and solver. The alternative model assumptions are
the red/blue-swapped training PSFs and a channel-average PSF. A control whose
training operator is purposely mismatched to the target-generator can
perform worse **by construction**: parameter matching does not remove that
confound. Models are evaluated in the R3 toy multi-wavelength profiles
using the frozen R4 signed-template metric. No real eye, monitor, comfort
or therapeutic outcome is measured. [R5 protocol](../experiments/r5_equal_capacity_controls/README_FA.md).

R5 completed in GitHub Actions: 12/12 **synthetic** comparisons favored
correct optical-channel mapping over independently optimized R/B-swapped
and channel-average PSF fit models (median scores +0.6686, +0.6007, +0.4938).
Unlike the negative R4 score after swapping an **unrefitted** image, the
independently reoptimized R/B mapping had **positive** model-template alignment.
This changes the interpretation of R4: the sign reversal was not unavoidable.
See [R5 results](../experiments/r5_equal_capacity_controls/RESULTS_REVIEW_FA.md).
The nominal target still favors the correct-fitting hypothesis, and color
artifact energy is not matched. These are not human eye measurements.

## Evidence gates
1. Check model optics, units, gamma and RGB spectral assumptions independently.
2. Replace restricted Gaussian rendering with physically constrained screen image optimization; include achievable intensity, clipping, and colorimetry.
3. Sweep viewing distance, pitch, pupil size, and display spectra; compare with achromatic and unmodified controls.
4. If Q1 is robust, pre-register objective dynamic autorefractor/photorefractor experiments, with expert oversight.
5. Only if Q2 succeeds, test comfort/strain against normal breaks in a controlled study (Q3).

Historical scripts and numerical files are under experiments/ and outputs/. No measured eyes or human subjects were used for current project results.

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

## R6 — synthetic identifiability challenge (under review)

R6 replaces the nominal R2 **training target generator** with the R3
`spectral_aberrated` alternative model. It is held out of evaluation.
The three 3HW RGB arms remain independently optimized under R2. After
fitting, all six RGB images per scene share the same assumed Rec.709
per-pixel linear luminance and a bounded mean chroma-deviation proxy,
without intensity clipping. A separate ablation repeats green-channel
optics across R/G/B to remove **all interchannel PSF differences**.
Undefined signed-template scores must be preserved as such.

The altered target source and matching budget are **in-silico audit tools**,
not real data, and do not validate any human accommodative response.
See [R6 preregistered protocol](../experiments/r6_identifiability/README_FA.md).

## R6 — review complete: previous strong superiority claim not robust

The CI R6 pilot completed 10/10 matched synthetic comparisons. Mapped RGB
outscored the independently reoptimized R/B-swapped PSF arm in 10/10, but
only outscored the **achromatic training-PSF** null in 2/10 after
luminance/chroma-proxy normalization. Median signed scores: mapped 0.12650,
permuted 0.11794, achromatic 0.14172. The target-generator was R3's toy
spectral_aberrated profile, held out from five toy scoring profiles.

The all-channel green-PSF negative control produced wildly unstable A scores
when synthetic +/- target templates were almost degenerate. Therefore the
signed-template metric needs a preregistered conditioning criterion before
further scientific claims. The current design **does not identify the causal
role of LCA or predict actual human accommodation**.
[Detailed reviewed R6 results](../experiments/r6_identifiability/RESULTS_REVIEW_FA.md).

## R7 — metric-identifiability audit (numerical pilot completed)

R7 responds to R6's inflated signed-template scores when +/- target
images became nearly indistinguishable. The original R4 formula is
retained for **audit only**, but its usable counterpart abstains
when the synthetic target-pair RMS difference is below a preregistered
numeric resolution heuristic: max(10*sqrt(2)/(255*sqrt(12)),
0.02*target RMS). Neither term is actual optical uncertainty or a
valid 10-sigma inferential statement.

A separate target-template-free *open-loop* 7-step focus scan scores
the gradient energy of the modeled retinal image and reports a
sampled sharpness peak and full-curve differences. An all-channel
green-PSF control removes every interchannel optics difference
(not selectively LCA). No human eye has been measured, and
a sharpness-model optimum is not an accommodation response.
[Scientific preregistration](../experiments/r7_metric_validation/README_FA.md).

R7 completed its frozen synthetic 10-pair study with all CI jobs passing.
The preregistered separation screen retained 10/10 regular target
pairs and correctly abstained on 10/10 common-green-PSF target pairs.
A separate open-loop model-only gradient-focus proxy found **zero
differences in discrete preferred focus** between the + and -
stimuli in all 3 RGB candidate arms across 10 profiles (0.25 D grid).
The curves themselves varied but did not show a peak displacement.
The findings limit interpretations of earlier template scores and
do not demonstrate actual human accommodation.
[Results review](../experiments/r7_metric_validation/RESULTS_REVIEW_FA.md).

## R8 — synthetic focus/spectral sensitivity (numerical pilot complete)

R8 extends the **open-loop, target-free synthetic sharpness scan**, not the
eye-break application. Its 432 correlated rows span 4 artificial scenes,
4 **toy** RGB primary spectrum/gamma cases, 3 independently optimized
color-proxy matched R6 RGB arms, 3 numerical focus measures, and 3 nested
grid steps. Scores are reported alongside predeclared ABSTAIN flags for
near-tied, flat or boundary peaks and a strong all-common-green-PSF
control. No statistically independent participant replication or observed
human accommodation is involved.

The wavelengths and gamma are **hypothetical uncertainty cases**, never
measured display SPDs, measured EOTF or physical confidence intervals.
[Scientific R8 preregistration (Persian)](../experiments/r8_sensitivity/README_FA.md).

The frozen R8 pilot finished **432 related synthetic numerical cells**
with 397 reportable focus peak comparisons, 35 near-tie abstentions,
and 96 small positive nonzero shifts, all at 0.125 or 0.0625 D
simulation-grid spacing. There were **0** nonzero shifts at 0.25 D,
reproducing the coarser R7 null. All-common-green-PSF controls
showed **zero peak displacement in 432/432** but some nonzero curve
difference under digitization/gamma assumptions. Results depend
on scene spatial structure, sharpness metric and unmeasured toy
RGB spectral assumptions. The achromatic-trained RGB null
produced more nonzero shifts than nominal-mapped RGB, so a
specific causal LCA-driven human response is **not identified**.
[Reviewed R8 results](../experiments/r8_sensitivity/RESULTS_REVIEW_FA.md).

## R9 — measurement feasibility without mandatory equipment acquisition

R8's numerical focus-peaks remained strongly metric, grid, scene and
toy spectrum dependent; Q1 physical stimulus feasibility, Q2 measured
ocular accommodation and Q3 symptom benefit are unvalidated.
R9 therefore pauses additional visual effect development and
establishes **four conditional routes**: P0 no-instrument document/data
analysis; P1 borrowed colorimeter for measured XYZ/luminance/EOTF;
P2 borrowed spectrometer capable of measuring real display emission
SPD; and P3 a separate expert-/ethics-reviewed human objective-eye
study. Any route can remain unavailable. Procurement is NOT required.

The default inventory records **UNKNOWN** hardware access rather than
assuming a particular display, instrument, source spectral dataset or
approval. A versioned Python feasibility assessment outputs
`FEASIBILITY_ONLY_NO_OBSERVATIONS` and cannot authorize use of humans
or upgrade evidence claims.
[Feasibility review (Persian)](../experiments/r9_measurement_readiness/FEASIBILITY_REPORT_FA.md).

## R10 — optional phone camera + empirical human perception feasibility

Equipment-based display SPD/EOTF and objective accommodative readings
are **optional future validation branches**, not technical blockers for
a separate adult-voluntary **perceptual feasibility** pilot.
R10's proposed H1 outcomes are reading accuracy, perceived image
clarity, comfort, interruptions/adverse events and response
completion, **not direct accommodation or relief of eye strain**.

Camera H1-VIDEO is **optional, with separate consent**; offline manual
blink annotations or pupil/iris relative ratios are exploratory,
illumination-confounded behavioral proxies. The provided research-only
Python planner never opens a camera or displays optical stimuli and
contains no participant data. R10 has **no actual human measurements yet**.
Stimulus-safety review, withdrawal ability, privacy and locally applicable
ethics clearance remain prerequisites to participating; no specialist
instrument or purchase is required for these safeguards.
[Research plan (Persian)](../experiments/r10_human_feasibility/PROTOCOL_FA.md)
 · [Safety/consent](../experiments/r10_human_feasibility/CONSENT_AND_SAFETY_FA.md).

## R11 — static candidate/control scene preflight (pending operator review)

R11 uses four matched word scenes rendered as low-contrast, static
RGB PNGs: an achromatic control (X) and a weak color-opponent
edge variant (Y). A numerical preflight checks model-space assumed
luminance and 8-bit color spread, with exact output hashes. The
**physical display is not calibrated**, no images are automatically
presented, and the candidate images remain labeled NOT APPROVED.
Even static, moderate-contrast pictures need a separate visual
risk review and documented locally appropriate participant consent
before H1. The R10 no-equipment study may continue after that;
Q2 objective accommodation measurement remains optional/unavailable.
[R11 preregistered protocol](../experiments/r11_static_stimuli/PROTOCOL_FA.md).

## R12 — R11 image readability audit and higher-contrast candidate review

Digital visual inspection of R11's four X/Y pairs showed very faint
large text; assumed model luminances (0.37 foreground, 0.54
background) imply a **1.40:1 model contrast ratio**. This could
confound a reading-response feasibility study. R12 introduces a
separate static image set using 0.14 foreground / 0.56 background,
giving a **~3.21:1 model design target**. The 3:1 number is drawn
from large-text accessibility guidance, not an epilepsy,
medical or universal human-study safety threshold.

An offline gate validates image SHA-256 and captures operator
review statuses on the *actual monitor*, consent, privacy and
locally applicable ethics determination. The default record
always remains PENDING. **Even a completed checklist is not
authorization to begin participant exposures.** No one has been
tested; no human eyes, accommodation or actual monitor EOTF
were measured. Optional phone camera remains off by default.
[Persian protocol/findings](../experiments/r12_display_review/PROTOCOL_AND_FINDINGS_FA.md).

## Evidence gates
1. Check model optics, units, gamma and RGB spectral assumptions independently.
2. Replace restricted Gaussian rendering with physically constrained screen image optimization; include achievable intensity, clipping, and colorimetry.
3. Sweep viewing distance, pitch, pupil size, and display spectra; compare with achromatic and unmodified controls.
4. If Q1 is robust, pre-register objective dynamic autorefractor/photorefractor experiments, with expert oversight.
5. Only if Q2 succeeds, test comfort/strain against normal breaks in a controlled study (Q3).

Historical scripts and numerical files are under experiments/ and outputs/. No measured eyes or human subjects were used for current project results.

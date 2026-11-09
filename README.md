# GazeBloom 🌱

**Explore gentler screen breaks and visual focus cues — with evidence before claims.**

GazeBloom is an open research-to-app project exploring visual stimuli, ocular accommodation, and the possibility of a future screen-break / eye-exercise application for people who spend long hours at a monitor.

> **Research status (November 2026):** Computational prototypes only. No human accommodation response or reduction in digital eye strain has been demonstrated by this project. The examples are **not** a validated eye exercise, medical device, or therapy.

## Evidence-informed screen-break app track (November 2026)

The **primary product goal** is now a privacy-first, user-controlled reminder application for screen breaks and comfortable visual habits. This is separate from the exploratory Chromablur optics project.

- [Evidence review (Persian)](docs/EVIDENCE_REVIEW_FA.md)
- [Proposed interventions (Persian)](docs/INTERVENTIONS_V1_FA.md)
- [Low-cost study proposal (Persian)](docs/LOW_COST_EVALUATION_FA.md)
- [MVP functional specification (Persian)](docs/MVP_SPEC_FA.md)
- [Machine-readable intervention safety/evidence catalog](research/evidence_catalog.json)

Research status: **no objective human accommodation measurements and no validated GazeBloom reduction in digital eye strain**. Literature shows mixed break-schedule results; the app will avoid therapeutic claims. The existing image/video experiments are not included as a default screen-break exercise.

## Experimental desktop reminder v0

The first **manual, offline-first screen-break reminder** prototype uses standard-library Tkinter:

```bash
sudo apt install python3-tk                 # Ubuntu: OS library
uv sync --python /usr/bin/python3 --no-managed-python --locked
uv run --python /usr/bin/python3 --no-managed-python --locked \
  python -m gazebloom --interval-min 10
```

No logging by default. Add explicit `--log ~/gazebloom-events.jsonl` to save event-only records locally. No eye measurement, verified screen-viewing time or efficacy is claimed. [Instructions and limitations (Persian)](docs/DESKTOP_REMINDER_V0_FA.md).

## Optional Linux idle-aware reminders (experimental)

The default remains a manual timer. To **opt in** to input-idle-based countdown holds:

```bash
uv run --python /usr/bin/python3 --no-managed-python --locked \
  python -m gazebloom --idle-aware --idle-threshold-sec 60
```

GNOME on Wayland or X11 may provide Mutter D-Bus idle information; X11 can optionally use `xprintidle`. Unsupported systems continue with the standard manual timer. **Keyboard/mouse inactivity is not verified screen viewing or measured eye physiology.** See [idle setup and limits (Persian)](docs/IDLE_AWARE_FA.md) and [application architecture](docs/ARCHITECTURE.md).

## What is here?

| Area | Contents | Status |
| --- | --- | --- |
| [`experiments/gaussian_lca_v0`](experiments/gaussian_lca_v0) | Initial Gaussian + longitudinal chromatic aberration (LCA) visual stimulus generator: near/far still images and two short videos | Exploratory illustration, **not** an exact reproduction of ChromaBlur |
| [`experiments/waveoptics_q1_v1`](experiments/waveoptics_q1_v1) | Scalar wave-optics PSF model, RGB blur optimization, offline tests, and a separate **future-data-only** accommodation analysis tool | Simulation; Q1 remains unresolved |
| [`outputs/`](outputs) | Historical numerical results on GitHub; complete original images, videos, plots and manifests in the [companion full-project archive](docs/IMPORT_BINARY_OUTPUTS_FA.md) pending one-time binary import | **Not recordings of a human eye** |
| [`docs/RESEARCH_STATUS.md`](docs/RESEARCH_STATUS.md) | Questions, assumptions, current evidence, limitations, and next steps | Active research record |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Research-to-app milestones | Proposed, not implemented |
| [`docs/SAFETY.md`](docs/SAFETY.md) | Safe interpretation and boundaries | Required context |

## Package management: uv

The standard GazeBloom workflow uses [uv](https://docs.astral.sh/uv/). `pyproject.toml` contains application and optional `research` dependencies; `uv.lock` pins exact resolutions. **Tkinter is native to the selected Python build** and is not installed from PyPI. For Ubuntu with Linuxbrew Python, see [the interpreter / uv guide](docs/UV_SETUP_FA.md).

```bash
uv sync --locked --extra research
uv run --locked --extra research python -m unittest discover -s tests -v
```

## Scientific experiments with uv

Use the optional `research` extra; no direct `pip install` or global site-packages changes:

```bash
uv sync --locked --extra research

# Offline numerical consistency checks
uv run --locked --extra research python experiments/gaussian_lca_v0/test_model.py
uv run --locked --extra research python -m unittest discover -s experiments/waveoptics_q1_v1 -p 'test_*.py' -v

# Regenerate media into a different directory (do not overwrite historical evidence)
uv run --locked --extra research python experiments/gaussian_lca_v0/chromablur_pilot.py \
  --out outputs/reproduction/pilot --distance-m 0.60 \
  --pixel-pitch-mm 0.27 --pupil-mm 4 --amplitude-d 0.45 \
  --seconds 10 --fps 15

uv run --locked --extra research python experiments/waveoptics_q1_v1/waveoptics_validation.py \
  --out outputs/reproduction/q1 --distance-m 0.60 \
  --pitch-mm 0.27 --pupil-mm 4 --delta-D 0.45
```

Historical PNG/MP4 and numerical outputs are research simulations, not human eye recordings; regenerated bytes may differ across systems.

## Current research priority: Track B / R1 (wave-optics audit)

The desktop app is in maintenance-only mode while we validate the simplified
optical model's internal consistency and parameter sensitivity. **This is not
a measured eye response or evidence of treatment benefit.**

```bash
uv sync --locked --extra research
uv run --locked --extra research python experiments/r1_model_sensitivity/sweep.py \
  --preset pilot --out outputs/reproduction/r1_pilot
```

The pilot studies a declared **16-case model grid, each with positive and negative
defocus**, and produces CSV, JSON, SHA-256 manifest, and a model-fit plot.
See [Track B R1 protocol (Persian)](experiments/r1_model_sensitivity/README_FA.md)
for its numerical limitations and interpretation.

Pilot verification on GitHub Actions (2026-11-04): **16 configurations, 32 model rows**.
The median per-channel PSF residual is **0.7174** (normalized L2, not a
percentage of visual/ocular error); the median fit advantage over a shared
RGB Gaussian is **2.37%**, with higher model flexibility. This **does not**
establish retinal accuracy, accommodation change, or eye-strain benefit.
See [reviewed R1 results (Persian)](experiments/r1_model_sensitivity/RESULTS_REVIEW_FA.md)
and [versioned simulation CSV](outputs/r1_pilot_v1/sweep.csv).

## Active Track B research: R2 bounded RGB image inversion

After the R1 PSF-only audit, the next experiment optimizes the **displayed RGB pixel values**
under a normalized [0,1] intensity constraint, and predicts their retinal appearance
using the **same simplified, fixed-focus eye model**. It includes a stronger optimized
grayscale-image control, 8-bit gamma tests and pupil-parameter perturbations.

```bash
uv run --locked --extra research python experiments/r2_display_inverse/pilot.py \
  --out outputs/reproduction/r2_pilot
```

**Important:** numerical image reconstruction on the same simulator used for optimization
does *not* verify actual accommodation or eye-strain relief. The display spectral power
distribution, measured gamma, viewer-specific aberrations and out-of-model testing are
not yet covered. See [R2 scientific protocol (Persian)](experiments/r2_display_inverse/README_FA.md).

## Track B R3 — model-mismatch stress evaluation

R2 is merged. The next stage freezes two synthetic scene families and six
alternative forward-optics/display profiles (24 rows across both defocus signs).
The R2-optimized images are evaluated with a **separate toy forward simulator**
that includes polychromatic primary samples, synthetic astigmatism/coma, gamma
mismatch and channel leakage. It is still simulation, not calibrated optics.

```bash
uv run --locked --extra research python experiments/r3_model_mismatch/evaluate.py \
  --out outputs/reproduction/r3_mismatch
```

See the [R3 protocol (Persian)](experiments/r3_model_mismatch/README_FA.md).
R3 cannot establish human accommodation or therapeutic benefit.

### R3 completed synthetic pilot (November 8, 2026)

All **24/24 frozen in-silico stress comparisons** favored optimized RGB over
optimized shared-gray on the **alternative synthetic forward model**.
Median relative retinal-image L2 discrepancy: **0.04725 RGB**, versus
**0.07888 gray** and **0.09661 unmodified**. Gamma mismatch worsened fit.
This is **not** independent physical validation, measured ocular accommodation,
or evidence of an effective screen exercise. See the
[R3 reviewed results (Persian)](experiments/r3_model_mismatch/RESULTS_REVIEW_FA.md)
and [exact archived CSV](outputs/r3_mismatch_v1/stress.csv).

## Track B R4 — signed chromatic-template controls

The active in-silico research stage tests if the RGB-optimized pattern's
**signed model-template alignment** depends on its actual red/blue assignment.
A red/blue channel swap preserves the same numeric RGB pixel field values and
effective channel capacity but scrambles the optical channel mapping. It is
not a separately optimized null or a measured accommodation response.

```bash
uv run --locked --extra research python experiments/r4_directional_controls/evaluate.py \
  --out outputs/reproduction/r4_directional
```

See the [R4 protocol (Persian)](experiments/r4_directional_controls/README_FA.md).
Even positive directional scores do **not** demonstrate eye accommodation,
safety, or therapeutic benefit.

### R4 numerical results (November 8, 2026)

In a **12-pair synthetic** alternative-optics evaluation, optimized RGB
achieved positive signed template alignment in **12/12** profiles and outscored
the red/blue-swapped equal-value RGB control in **12/12**. Median signed
alignment: RGB **+0.6686**, swapped RGB **−0.6016**, optimized gray **+0.0096**.
This identifies color-channel mapping sensitivity *within these models*;
it is **not** measured accommodation, true optical feasibility, or therapy.

See [R4 scientific review (Persian)](experiments/r4_directional_controls/RESULTS_REVIEW_FA.md),
[exact 12-row CI CSV](outputs/r4_directional_v1/direction.csv), and
[model provenance](outputs/r4_directional_v1/manifest.json).

## Track B R5 — independently optimized RGB control arms

The next in-silico research gate tests **three RGB hypotheses at exactly the
same 3HW free-variable capacity** (correct optical channel mapping, switched
red/blue PSF mapping, and channel-averaged PSF), each fitted **independently**
under the same source, fixed synthetic target, regularizers, initial pixel
values, RGB bounds and optimizer. Compare on R3's 6 held-out toy profiles
for 2 synthetic scenes and signed ±0.45 D targets.

```bash
uv run --locked --extra research python experiments/r5_equal_capacity_controls/evaluate.py \
  --out outputs/reproduction/r5_equal_capacity
```

The nominal target is generated by the correctly specified R2 optics, making
the wrong-mapping nulls intentionally disadvantaged by model misspecification.
Matching parameter count alone is **not** a causal proof of chromatic guidance;
see [R5 protocol (Persian)](experiments/r5_equal_capacity_controls/README_FA.md).

### R5 completed in-silico comparison (2026-11-08)

Three independently fitted **3HW-parameter RGB** arms were compared on
12 paired synthetic R3 model profiles. The original optical-channel mapping
outscored the independently reoptimized R/B-swapped training model and the
achromatic-PSF model in **12/12**, with median signed template scores
**+0.6686**, **+0.6007** and **+0.4938**, respectively.

Most importantly, the R4 negative score for a *simple swap of a previously
fitted image* became **positive** after independently refitting the null.
A channel-order swap of an unrefitted image is therefore not proof of
unavoidable opposite-direction retinal cues, still less a human accommodation
response. The nominal target was generated by the correct-mapping model;
capacity matching alone does not remove this model-favoring confound.

[Scientific R5 review (Persian)](experiments/r5_equal_capacity_controls/RESULTS_REVIEW_FA.md)
 · [Original 12-row CSV](outputs/r5_equal_capacity_v1/equal_capacity.csv)
 · [CI summary](outputs/r5_equal_capacity_v1/summary.json).

## Track B R6 — cross-generator targets and matched chroma/luminance

R5's nominal target was built using the same optical model that trained the
correct-mapping arm. R6 now constructs the *training target* using a **different
R3 synthetic optical engine** (polychromatic and aberrated) while independently
training the same three RGB fit hypotheses under R2. The target-generating
profile is excluded from scoring; 2 scenes × 5 other profiles = 10 paired
synthetic stress comparisons.

All three fitted arms are also scored after a shared **assumed Rec.709 linear
luminance** and identical mean chromatic-deviation budget, achieved with
nonamplifying, gamut-preserving scaling. An all-green-OTF optical ablation
removes every interchannel PSF difference; this is *not an isolated LCA
knockout* and can give an undefined signed-template metric.

```bash
uv run --locked --extra research python experiments/r6_identifiability/evaluate.py \
  --out outputs/reproduction/r6_identifiability
```

These are not calibrated displays, measured retinal images, human
accommodation, or clinical claims. See the
[R6 research protocol (Persian)](experiments/r6_identifiability/README_FA.md).

### R6 outcome: original-mapping advantage failed the stronger null (2026-11-09)

With externally generated *synthetic* training targets and equal assumed
Rec.709 luminance/chroma-proxy budgets, original RGB still outscored the
independently refitted swapped-PSF RGB in **10/10**, but outscored the
independently optimized achromatic-PSF RGB in just **2/10** artificial profiles.
Median signed template alignment after matching: mapped **0.12650**,
swapped **0.11794**, achromatic training PSF **0.14172**.

The channel-identical-PSF negative control also exposed a serious
**near-degenerate-target / ill-conditioned score** problem: signed scores
can explode to +41 or −59 despite the model templates being almost identical.
This invalidates a strong interpretation of the R5 mapping advantage.
It **does not** disprove physical chromatic-accommodation research, nor
establish any response of human eyes. Prioritize metric identifiability
and display characterization before generating new "eye exercises."

[Full R6 scientific review (Persian)](experiments/r6_identifiability/RESULTS_REVIEW_FA.md)
 · [Exact CI CSV](outputs/r6_identifiability_v1/identifiability.csv)
 · [Source provenance](outputs/r6_identifiability_v1/manifest.json).

## Track B R7 — stability of directional metrics

R6 showed that the original RGB superiority did not survive a stronger
achromatic control after numerical color matching. Worse, the signed
template score had values near +41 and -59 when positive and negative
optical templates became nearly identical.

R7 now introduces an explicitly preregistered conditioning threshold. If
target separation is too small relative to a numeric noise-resolution
heuristic, the usable score is abstained, while the historical raw score
is retained solely for audit. Separately, an open-loop simulated
sharpness/focus scan uses no synthetic target template; it is a
computational autofocus proxy and **not** predicted human accommodation.

The experiment reuses R6 color-proxy matching and 2 scenes x 5 held-out
synthetic profiles. It includes a green-OTF-on-all-channels control.

See [the Persian R7 protocol](experiments/r7_metric_validation/README_FA.md).
Neither model numerics nor simulated focus preferences validate real
retinal optics, effective eye exercises, or health outcomes.

### R7 completed: conditioned template and target-free scan (2026-11-09)

In the frozen 10-pair synthetic R7 run, all 10 common-green-PSF
negative controls were flagged **ABSTAIN** under the preregistered numeric
separation threshold. All 10 regular profiles passed the conditioning
check. The earlier R6 result remained: mapped RGB outscored the
achromatic-PSF trained RGB control in just 2/10.

A separate target-template-free focus scan found **no shift of the
discrete sharpness peak** between + and - stimulus designs in any of
the 3 RGB arms or 10 profiles (0.25 D grid). Full sharpness curves
differed, but curve variation does not establish changed focus.
Common-green PSF removed the differences almost entirely except
for a residual in a toy channel-leakage model.

These are only **synthetic scalar-optics diagnostics**, not eye
accommodation measurements, validated eye exercises or proof of
clinical benefit.

[Full scientific review (Persian)](experiments/r7_metric_validation/RESULTS_REVIEW_FA.md)
and [versioned CI data](outputs/r7_metric_validation_v1/r7_metrics.csv).

## Track B R8 — preregistered sensitivity of the simulated autofocus proxy

R7 showed no shift of the discrete sharpness optimum despite differences
in the full synthetic focus curves. R8 tests whether this result depends
on the selected sharpness function, simulated focus-grid spacing, scene
content, or unmeasured hypothetical display primary spectra/gamma.

It freezes **4 synthetic scenes × 4 toy spectral cases × 3 RGB arms ×
3 autofocus metrics × 3 nested focus grids = 432 related numerical rows**.
Three metrics are central gradient energy, Laplacian energy, and
Fourier band power; grid spacings are 0.25, 0.125 and 0.0625 D.
A numerical peak is abstained if its two best scores are near-tied,
its curve is too flat, or its maximum is at the search boundary.
All raw, reportable, abstained and common-channel-optics-null results
must be retained.

```bash
uv run --locked --extra research python experiments/r8_sensitivity/evaluate.py \
  --out outputs/reproduction/r8_sensitivity
```

The 3-point spectra, primary shifts and gamma are **not measured SPDs or
a calibrated EOTF**. None of the metrics is an objective measurement or
credible prediction of human accommodation, eye strain, or efficacy.
[R8 preregistered protocol (Persian)](experiments/r8_sensitivity/README_FA.md).

### R8 completed synthetic focus and spectrum sensitivity (2026-11-09)

The complete preregistered **432-row** in-silico study found 397
numerically reportable paired-peak comparisons and 96 small nonzero
shifts (+0.0625 D or +0.125 D in the *simulation grid* only).
There were **0/144 at focus step 0.25 D**, 41/144 at 0.125 D,
and 55/144 at 0.0625 D, with 35 near-tie abstentions overall.
All 432 common-green-PSF controls had **zero raw peak displacement**.

Findings are sensitive to **metric, scene content and toy spectral
assumptions**, and the achromatic-PSF *training* RGB null produced
more nonzero shifts (41) than the nominal RGB mapping (29).
A finer optical simulation grid is **not** proof of measured human
accommodation, causal LCA, optical display validity or relief of eye strain.
The next justified stage is independent **display SPD/EOTF and eye-optics
measurement planning**, rather than iterating arbitrary visual effects.

[Full R8 science review (Persian)](experiments/r8_sensitivity/RESULTS_REVIEW_FA.md)
 · [Exact 432-row CI CSV](outputs/r8_sensitivity_v1/sensitivity.csv)
 · [Provenance hashes](outputs/r8_sensitivity_v1/manifest.json).

## Core research questions

- **Q1 — optical feasibility:** Can a static-screen image reproduce a desired *modeled retinal blur cue* under declared assumptions?
- **Q2 — physiology:** When tested with calibrated dynamic autorefraction/photorefraction, does the stimulus actually cause a predictable change in ocular accommodation?
- **Q3 — benefit:** If Q2 is supported, does any intervention reduce digital eye strain more than matched normal breaks, in a controlled study?

**Q1 is not yet established.** In the earlier restricted Gaussian-PSF optimization the per-channel model improved the normalized error relative to a common RGB-blur control by only **1.35% (near) / 1.49% (far)**; these are *deterministic simulation comparisons*, not physiological or clinical effect sizes. **Q2 and Q3 have no human data.**

## Why ChromaBlur?

Chromatic defocus cues are a plausible software-only candidate for studying accommodation on a conventional flat screen. GazeBloom does **not** claim that changing RGB blur can move the screen's physical focal plane, that the current model replicates the original research apparatus, or that it will relax/train the ciliary muscle.

Related work: Cholewiak et al., *Creating Correct Blur and Its Effect on Accommodation*, 2018 — https://pmc.ncbi.nlm.nih.gov/articles/PMC6126933/ . The code in this repository is **independent exploratory code**, not the paper's released implementation.

## Future app scope

The eventual product may combine screen-break reminders, comfortable distance-view prompts, accessibility, and **only validated** visual exercises. For now, the repository contains the research foundation, **not a finished app**. See [roadmap](docs/ROADMAP.md).

## Language / license

Most historical technical documents are in Persian; this README provides an English entry point. No open-source license has been selected yet; do not assume permission to redistribute or reuse the code beyond rights granted by applicable law. Repository owner can add a license after choosing one.
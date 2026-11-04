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
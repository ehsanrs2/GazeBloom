# GazeBloom roadmap — evidence before claims (2026-11-08)

## Track A — practical screen-break app (maintenance only during active Track B research)
- [x] Target use case fixed: screen breaks and low-risk visual-wellness behavior.
- [x] Initial evidence register, explicit confidence boundaries, intervention catalogue and low-cost evaluation proposal.
- [x] R10 human-perception *protocol* for voluntary static A/B readability and comfort, opt-in phone video proxies and private data management (without physical optics instruments).
- [x] R11 implement deterministic four paired static grayscale / weak-chroma candidate PNGs with numeric luminance/range audits and exact image SHA-256 manifests; files are **NOT APPROVED for human use**.
- [x] R12 visually inspect *digital* R11 still images and identify modeled contrast ≈1.40:1 as a risk of near-floor readability; preserve R11 artifact, prepare a new separate higher-legibility four-pair set.
- [x] Implement R12 candidate generator with model-only ≥3:1 large-word contrast, exact source-image hashes and offline real-display/consent/ethics checklist with no self-authorization.
- [x] R13 implement explicit operator-only Tk static image review (NO autonomous participant presentation), private R12 SHA-256-pinned checklist creation and per-word balanced X/Y binding to R10 eight-trial plan.
- [ ] R13 operator actually reviews eight image files on the intended monitor and records real-world image/lighting/comfort checks; **not completed by CI or PR merge**.
- [x] R14 implement pure virtual-time H1 state machine for max 10-second view, min 30-second rest, explicit next, irreversible STOP from all active phases, and discomfort-driven terminal stop; strengthen R10 response parser against post-stop/ordered-data violations.
- [x] R14 create operator-only neutral-text Tk demonstration, fake time/STOP CI cases, and **unapproved** Persian draft consent, privacy/retention and independent ethics review documents.
- [ ] Operator actually tests the R14 no-stimulus timer/STOP UI on local monitor and records usability; CI does not verify OS display timing or actual stop accessibility.
- [ ] Independent review of final informed consent, real data retention/deletion, optional camera consent and applicable ethics requirement/approval before H1. Reported R13 20/25 is not authorization; never auto-toggle checkboxes.
- [ ] Independently authorize specific R12 still PNGs, real display procedure and release an H1 participant runner only after all jurisdiction-dependent gates. Direct accommodation measurement remains optional, unavailable and scientifically separate.
- [ ] Determine locally applicable ethics/consent requirements and explicitly approve specific R11 static candidate/control images and safe stop procedures **before inviting participants**; neither scripts nor CI authorize testing.
- [ ] Conduct H1 participant feasibility pilot only after these safeguards, using real opt-in responses; do not publish identifiable footage or interpret subjective responses as accommodation.
- [x] Monotonic-clock timer, private opt-in local event log and first manual desktop Tkinter UI.
- [x] Build opt-in Linux idle-awareness probe (GNOME D-Bus / X11 xprintidle), conservative hold policy and offline tests.
- [x] Owner reported successful manual idle-aware behavior on Ubuntu (2026-11-04); platform-wide suspend/Wayland matrix remains untested.
- [ ] Broader suspend/wake and other desktop-compositor validation after research milestone.
- [ ] Cross-platform notifications, tray integration, versioned settings, accessible/localized UI and packaging.
- [ ] Test notification state machine, idle detection, pause/snooze, user control, performance and privacy.
- [ ] Conduct small consent-based feasibility pilot (reported symptoms and behaviors, not optics).
- [ ] Review evidence and usability findings before any public efficacy claims.

## Track B — active research priority (isolated from wellness claims)
- [x] Gaussian + LCA images and video exploratory generator.
- [x] Scalar wave-optics PSF simulation and synthetic-data Q2 analysis code.
- [x] R1 numerical-invariant checks, descriptive FFT-grid convergence audit and deterministic model sensitivity runner.
- [x] Execute and inspect full R1 16-case / 32-row pilot, including absolute residuals and a single-case FFT-grid comparison ([review](../experiments/r1_model_sensitivity/RESULTS_REVIEW_FA.md)).
- [ ] Independently validate physical units and PSF sampling accuracy across multiple pupil/defocus scenarios.
- [x] R2 bounded, image-specific RGB inverse optimization with [0,1] ideal linear-intensity constraints, optional chroma penalty and gamma perturbations (research prototype).
- [x] Review R2 pilot ([numerical report](../experiments/r2_display_inverse/RESULTS_REVIEW_FA.md)); RGB fits better on the same model, but physical Q1 remains unresolved.
- [x] Implement R3 alternative-polychromatic forward simulator, synthetic aberrations and 24-row frozen mismatch protocol.
- [x] Review R3 24-row synthetic mismatch output: RGB won all artificial profiles, yet physical validity remains unresolved ([report](../experiments/r3_model_mismatch/RESULTS_REVIEW_FA.md)).
- [x] Implement R4 signed-template score, RGB red/blue-swap capacity-preserving null and numerical color-artifact proxies; results not yet reviewed.
- [x] Review all 12 R4 paired model outputs: RGB signed alignment positive and R/B-swapped negative across frozen synthetic profiles; no human validation ([review](../experiments/r4_directional_controls/RESULTS_REVIEW_FA.md)).
- [x] R5 implementation: two independently fitted 3HW RGB null optical operators (R/B swapped PSF and achromatic PSF), with identical synthetic targets and optimization constraints; results pending.
- [x] Analyze 12-row R5 independently optimized equal-3HW controls: mapped RGB wins all frozen synthetic profiles but reoptimized swapped/null models also retain positive signed alignment; [full review](../experiments/r5_equal_capacity_controls/RESULTS_REVIEW_FA.md).
- [x] Implement R6 independent **synthetic R3 target-generator** for all R2-trained arms, exact assumed-luminance/chroma-proxy matching, and all-channel identical-PSF negative control.
- [x] R6 10-row numerical results reviewed: mapped beats swapped in 10/10 but achromatic training-PSF null beats mapped in 8/10 **after proxy matching** ([review](../experiments/r6_identifiability/RESULTS_REVIEW_FA.md)).
- [x] Implement R7 preregistered numerical conditioning: abstain on near-degenerate synthetic +/- target separation instead of interpreting inflated A.
- [x] Implement a template-independent **open-loop** seven-sample synthetic gradient-energy focus scan, with common-green-PSF control; this is NOT measured accommodation or a physiological closed-loop model.
- [x] Review R7 frozen 10-pair data: common-green-PSF targets all abstain; regular targets all pass the numeric screen; no discrete focus-peak displacement in 3 RGB candidates ([review](../experiments/r7_metric_validation/RESULTS_REVIEW_FA.md)).
- [x] Preregister R8 432-row toy-spectrum / four-scene / three-sharpness-metric / nested-focus-grid sensitivity and frozen peak-abstention rules.
- [x] Review all R8 432 related comparisons: 0/144 discrete shifts at 0.25 D, 41/144 at 0.125 D, 55/144 at 0.0625 D; 35 near-tie abstentions and zero control peak shifts. Strong scene/metric/toy-spectra dependence; [R8 scientific review](../experiments/r8_sensitivity/RESULTS_REVIEW_FA.md).
- [x] R9 no-purchase feasibility specification: P0 public-data modeling, P1 colorimetry, P2 emissive spectra and P3 supervised objective accommodation, each with explicit evidence and safety gates; [Persian report](../experiments/r9_measurement_readiness/FEASIBILITY_REPORT_FA.md).
- [x] R9 conservative offline inventory/readiness validator: unknown or possible access cannot be treated as confirmed hardware or actual measurements.
- [ ] If no instrument exists: identify and verify licensed public display spectral data with SHA-256 and spectral instrument provenance; explore only other-display sensitivity modeling.
- [ ] If borrowing is possible: confirm instrument-specific capability, calibration, Linux support and data usage rights before any acquisition or study.
- [ ] Seek **actual** measured SPD/EOTF display parameters and independent optics; synthetic spectral shifts cannot satisfy this physical evidence gate.
- [ ] Independently calibrate display optics and build credible human-response evidence before any product claim.
- [ ] Build true display spectral/EOTF characterization, target-model uncertainty sweep and independent optics evidence before physical Q1 claims.
- [ ] Define psychophysical artifact limits and real display characterization before physical claims.
- [ ] Replicate with other scene families, measured RGB SPD/EOTF or independent optical measurements, and perceptual constraints.
- [ ] Calibrate actual display primaries/gamma and test with independent PSF model; [0,1] normalization alone is not full display-aware validation.
- [x] R1 pilot design sweeps distance, pixel pitch, pupil size and defocus sign/magnitude.
- [ ] Add measured RGB spectra, calibrated gamma and monitor brightness; these are not covered by R1.
- [ ] Literature-based synthesis; label predicted responses as hypotheses.
- [ ] **Direct measurement of human accommodation remains optional and unavailable** without a validated objective optical method and appropriate expertise. This does not block H1 perceptual/comfort observations with the separate R10 safety/consent gates.

## Constraints
- No therapeutic or muscle-strengthening claims.
- Subjective blur, comfort or perceived depth do not validate accommodation response.
- The first working app should not include experimental chromatic stimuli in default break exercises.
- See [evidence review](EVIDENCE_REVIEW_FA.md), [intervention catalog](INTERVENTIONS_V1_FA.md), [MVP spec](MVP_SPEC_FA.md), [proposed study](LOW_COST_EVALUATION_FA.md).

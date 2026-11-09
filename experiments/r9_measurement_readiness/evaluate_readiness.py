#!/usr/bin/env python3
"""Evidence-limited R9 feasibility gate, offline and with no instrument I/O.

A readiness flag indicates *potential to plan a measurement*, NOT
that any device was calibrated or any data were measured.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

STUDY = "GAZEBLOOM_R9_NO_PURCHASE_MEASUREMENT_READINESS_V1"
ACCESS = {"unknown", "unavailable", "candidate_loan", "verified_access"}
FIELDS = ("published_spd", "colorimeter", "spectrometer",
          "accommodation_instrument")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_known_access(record: dict) -> bool:
    return record["access"] == "verified_access"


def assess_inventory(data: dict) -> dict:
    """Do not allow proposals and loans to masquerade as measured evidence."""
    if not isinstance(data, dict) or data.get("project") != "GazeBloom_R9_FEASIBILITY":
        raise ValueError("wrong or missing project identity")
    if "observations" in data or "measured" in data or "validated" in data:
        raise ValueError("R9 readiness inventory does not accept observation claims")
    monitor = data.get("monitor")
    resources = data.get("resources")
    human = data.get("human_research")
    if not isinstance(monitor, dict) or not isinstance(resources, dict) or not isinstance(human, dict):
        raise ValueError("monitor, resources and human_research objects required")
    if not all(isinstance(resources.get(name), dict) for name in FIELDS):
        raise ValueError("four separate resource records required")
    for name, rec in [("monitor", monitor), *[(k, resources[k]) for k in FIELDS]]:
        access = rec.get("access")
        if access not in ACCESS:
            raise ValueError(f"{name}: invalid availability status: {access!r}")
    if monitor.get("serial_in_public_report") is not False:
        raise ValueError("avoid disclosing monitor serials or raw EDID in a public inventory")
    bool_fields = [
        monitor.get("settings_recorded"),
        resources["spectrometer"].get("emissive_mode_confirmed"),
        resources["accommodation_instrument"].get("operator_trained"),
        *(human.get(x) for x in
          ("ethics_approved", "supervisor_confirmed",
           "consent_protocol", "device_safety_reviewed")),
    ]
    if any(not isinstance(x, bool) for x in bool_fields):
        raise ValueError("readiness controls must use explicit true/false, not missing or strings")

    spd = resources["published_spd"]
    color = resources["colorimeter"]
    spectro = resources["spectrometer"]
    accommodation = resources["accommodation_instrument"]
    known_monitor = (monitor["access"] == "verified_access"
                     and _text(monitor.get("model"))
                     and bool(monitor["settings_recorded"]))
    external_data = (_is_known_access(spd) and
                     _text(spd.get("source_url")) and
                     _text(spd.get("license_note")) and
                     _text(spd.get("panel_match_note")) and
                     isinstance(spd.get("source_sha256"), str) and
                     SHA256_RE.fullmatch(spd["source_sha256"]) is not None)
    color_ready = (known_monitor and _is_known_access(color) and
                   _text(color.get("model")) and
                   _text(color.get("correction_reference")))
    spectral_ready = (known_monitor and _is_known_access(spectro) and
                      _text(spectro.get("model")) and
                      bool(spectro["emissive_mode_confirmed"]) and
                      _text(spectro.get("calibration_record")))
    eye_ready = (spectral_ready and _is_known_access(accommodation)
                 and _text(accommodation.get("model"))
                 and accommodation["operator_trained"]
                 and all(human[x] for x in (
                     "ethics_approved", "supervisor_confirmed",
                     "consent_protocol", "device_safety_reviewed")))
    flags = {
        "P0_document_and_model_audit": True,
        "P0_external_SPD_modeling_ready": bool(external_data),
        "P1_own_monitor_XYZ_EOTF_capture_ready": bool(color_ready),
        "P2_own_monitor_emissive_SPD_capture_ready": bool(spectral_ready),
        "P3_objective_eye_study_planning_ready": bool(eye_ready),
    }
    blockers = {
        "P0_external_SPD_modeling": (
            [] if external_data else
            ["Record source URL, license, SHA-256, panel-match caveat and verified access"]),
        "P1_colorimetry": (
            [] if color_ready else
            ["Confirm monitor model/settings and verified colorimeter access, model and display correction"]),
        "P2_spectra": (
            [] if spectral_ready else
            ["Confirm monitor/settings and emissive spectral instrument access, model, calibration record"]),
        "P3_objective_accommodation": (
            [] if eye_ready else
            ["Requires P2 readiness, objective measurement device, trained operator, oversight, ethics, consent and safety review"]),
    }
    if not external_data:
        next_action = "P0: search licensed published display spectra and record full provenance; no equipment purchase"
    elif not color_ready:
        next_action = "P0: run published-SPD-only simulations, label them external-display assumptions"
    elif not spectral_ready:
        next_action = "P1: plan repeatable display XYZ/EOTF measurement using confirmed access"
    elif not eye_ready:
        next_action = "P2: plan documented emissive display SPD measurement using confirmed access"
    else:
        next_action = "P3: expert-reviewed prospective design only; no human tests are authorized by this report"
    return {
        "study": STUDY,
        "inventory_date": data.get("updated_on"),
        "evidence_state": "FEASIBILITY_ONLY_NO_OBSERVATIONS",
        "readiness": flags,
        "blockers": blockers,
        "next_non_procurement_action": next_action,
        "permitted_evidence_claims": [
            "software_reproduction_and_model_uncertainty",
            "externally_published_SPD_may_support_other_display_scenario_only",
        ],
        "prohibited_claims": [
            "own_monitor_SPD_measured_from_inventory",
            "own_monitor_EOTF_measured_from_inventory",
            "retinal_PSF_or_human_accommodation_validated",
            "eye_strain_or_therapeutic_benefit",
        ],
        "human_participant_testing_authorized": False,
        "automatic_procurement_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path,
                        default=Path(__file__).with_name("inventory_template.json"))
    parser.add_argument("--out", type=Path, default=None,
                        help="optional output report; otherwise stdout only")
    args = parser.parse_args()
    report = assess_inventory(json.loads(args.inventory.read_text(encoding="utf-8")))
    result = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(result, encoding="utf-8")
    print(result, end="")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build audited-thickness cases with the pre-upper-bound HRRPUA values."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
Q_VALUES = (50, 100, 200, 300, 400)
UPPER_SUFFIX = "H1H7_v5_Qnorm_adapt_HRRupper_thickness_audit"
NOMINAL_SUFFIX = "H1H7_v5_Qnorm_adapt_HRRnominal_thickness_audit_v1"
MATERIAL_HRR = {
    "EBLXW": 75.0,
    "BXSSL": 250.0,
    "HYBLXW": 100.0,
    "JAZPM": 200.0,
    "PVCSL": 200.0,
    "CRXJ": 180.0,
}


def update_surface(match: re.Match[str]) -> str:
    block = match.group(0)
    material = re.search(r"MATL_ID\(1,1\)\s*=\s*'([^']+)'", block, flags=re.I)
    hrr = re.search(r"HRRPUA\s*=\s*[-+0-9.Ee]+", block, flags=re.I)
    if not material or not hrr:
        return block
    if material.group(1) == "NLZW":
        value = 180.0
    else:
        value = MATERIAL_HRR.get(material.group(1))
    if value is None:
        return block
    return re.sub(
        r"HRRPUA\s*=\s*[-+0-9.Ee]+",
        f"HRRPUA={value:.1f}",
        block,
        count=1,
        flags=re.I,
    )


def main() -> None:
    built = []
    for q in Q_VALUES:
        source_name = f"Q{q:04d}_W0100_az270_el15_{UPPER_SUFFIX}"
        case_name = f"Q{q:04d}_W0100_az270_el15_{NOMINAL_SUFFIX}"
        source = ROOT / "cases_adaptive" / source_name
        target = ROOT / "cases_adaptive" / case_name
        target.mkdir(parents=True, exist_ok=True)
        for name in ("monitor_registry.json", "flux_faces.csv"):
            shutil.copy2(source / name, target / name)
        text = (source / f"{source_name}.fds").read_text(encoding="utf-8", errors="replace")
        text = re.sub(
            r"(&HEAD\b[^/]*CHID\s*=\s*')[^']+(')",
            rf"\g<1>{case_name}\g<2>",
            text,
            count=1,
            flags=re.I,
        )
        text = re.sub(r"&SURF\b[\s\S]*?/", update_surface, text, flags=re.I)
        note = (
            "! Nominal HRRPUA campaign restored from the pre-upper-bound baseline.\n"
            "! Only HRRPUA changed; Q normalization, geometry, thickness, ignition,\n"
            "! BURN_AWAY, probes, grid and damage criteria are unchanged.\n"
        )
        (target / f"{case_name}.fds").write_text(note + text, encoding="utf-8")
        summary = json.loads((source / "case_summary.json").read_text(encoding="utf-8"))
        summary.update(
            case=case_name,
            mpi=20 if q == 50 else 32,
            purpose="nominal_HRRPUA_with_audited_thickness",
            source_case=source_name,
            changed_factor="HRRPUA_upper_to_nominal_only",
            hrrpua_group_values_kw_m2={
                "RADM": 75.0, "WINS": 250.0, "BED": 180.0, "CURT": 180.0,
                "U4": 100.0, "SEAT": 200.0, "H6": 200.0, "H7": 180.0,
            },
            hrrpua_parameter_class="nominal_pre_upper_bound_baseline",
            geometry_changed=False,
            thickness_changed=False,
            ignition_temperature_changed=False,
            burn_away_changed=False,
            probes_changed=False,
            damage_thresholds_changed=False,
        )
        (target / "case_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        built.append(case_name)
    manifest = {"cases": built, "Q_J_cm2": list(Q_VALUES)}
    (ROOT / "cases_adaptive" / "nominal_hrr_campaign_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

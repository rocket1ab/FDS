#!/usr/bin/env python3
"""Build the Q400 material-table HRRPUA sensitivity case."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "Q0400_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRnominal_thickness_audit_v1"
TARGET = "Q0400_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRtable_thickness_audit_v1"
HRR_BY_MATL = {
    "EBLXW": 75.0,   # RADM: no direct match in the supplied table
    "BXSSL": 250.0,  # WINS: no direct match in the supplied table
    "NLZW": 400.0,   # BED and CURT: nylon fabric
    "HYBLXW": 350.0, # U4: cockpit/electronic-equipment row
    "JAZPM": 450.0,  # SEAT: polyurethane foam
    "PVCSL": 200.0,  # H6: no direct match in the supplied table
    "CRXJ": 180.0,   # H7: no direct match in the supplied table
}


def update_surface(match: re.Match[str]) -> str:
    block = match.group(0)
    material = re.search(r"MATL_ID\(1,1\)\s*=\s*'([^']+)'", block, flags=re.I)
    if not material or material.group(1) not in HRR_BY_MATL:
        return block
    value = HRR_BY_MATL[material.group(1)]
    return re.sub(
        r"HRRPUA\s*=\s*[-+0-9.Ee]+",
        f"HRRPUA={value:.1f}",
        block,
        count=1,
        flags=re.I,
    )


def main() -> None:
    source = ROOT / "cases_adaptive" / SOURCE
    target = ROOT / "cases_adaptive" / TARGET
    target.mkdir(parents=True, exist_ok=True)
    for name in ("monitor_registry.json", "flux_faces.csv"):
        shutil.copy2(source / name, target / name)

    text = (source / f"{SOURCE}.fds").read_text(encoding="utf-8", errors="replace")
    text = re.sub(
        r"(&HEAD\b[^/]*CHID\s*=\s*')[^']+(')",
        rf"\g<1>{TARGET}\g<2>",
        text,
        count=1,
        flags=re.I,
    )
    text = re.sub(r"&SURF\b[\s\S]*?/", update_surface, text, flags=re.I)
    note = (
        "! Q400 material-table HRRPUA sensitivity case.\n"
        "! Only HRRPUA changed from the nominal Q400 control. Geometry, Q,\n"
        "! thickness, ignition, BURN_AWAY, probes, grid and criteria are unchanged.\n"
    )
    (target / f"{TARGET}.fds").write_text(note + text, encoding="utf-8")

    summary = json.loads((source / "case_summary.json").read_text(encoding="utf-8"))
    summary.update(
        case=TARGET,
        mpi=32,
        purpose="Q400_material_table_HRRPUA_sensitivity",
        source_case=SOURCE,
        changed_factor="HRRPUA_nominal_to_material_table_only",
        hrrpua_group_values_kw_m2={
            "RADM": 75.0,
            "WINS": 250.0,
            "BED": 400.0,
            "CURT": 400.0,
            "U4": 350.0,
            "SEAT": 450.0,
            "H6": 200.0,
            "H7": 180.0,
        },
        hrrpua_parameter_class="user_material_table_aligned",
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
    print(target)


if __name__ == "__main__":
    main()

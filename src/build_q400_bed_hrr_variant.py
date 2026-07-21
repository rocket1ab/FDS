#!/usr/bin/env python3
"""Build a Q400 BED-only HRRPUA upper-bound sensitivity case."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_NAME = "Q0400_W0100_az270_el15_H1H7_v5_Qnorm_threshold"
SOURCE = ROOT / "cases_threshold" / SOURCE_NAME
CASE_NAME = "Q0400_W0100_az270_el15_H1H7_v5_Qnorm_adapt_BED_HRRmax"
OUTPUT = ROOT / "cases_adaptive" / CASE_NAME
BED_HRRPUA_KW_M2 = 790.0


def build() -> Path:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in (f"{SOURCE_NAME}.fds", "monitor_registry.json", "flux_faces.csv", "case_summary.json"):
        shutil.copy2(SOURCE / name, OUTPUT / name)

    old_fds = OUTPUT / f"{SOURCE_NAME}.fds"
    new_fds = OUTPUT / f"{CASE_NAME}.fds"
    old_fds.replace(new_fds)
    text = new_fds.read_text(encoding="utf-8", errors="replace")
    text, head_count = re.subn(
        r"(&HEAD\b[^/]*CHID\s*=\s*')[^']+(')",
        rf"\g<1>{CASE_NAME}\g<2>", text, count=1, flags=re.I,
    )

    changed = 0

    def edit_surface(match: re.Match[str]) -> str:
        nonlocal changed
        block = match.group(0)
        if "MATL_ID(1,1)='NLZW'" not in block:
            return block
        thickness = re.search(r"THICKNESS\(1\)\s*=\s*([-+0-9.Ee]+)", block)
        if not thickness or float(thickness.group(1)) <= 0.05:
            return block
        block, count = re.subn(
            r"(HRRPUA\s*=\s*)[-+0-9.Ee]+", rf"\g<1>{BED_HRRPUA_KW_M2:.1f}",
            block, count=1, flags=re.I,
        )
        changed += count
        return block

    text = re.sub(r"&SURF\b[\s\S]*?/", edit_surface, text, flags=re.I)
    if head_count != 1 or changed < 2:
        raise RuntimeError(f"Unexpected replacement counts: HEAD={head_count}, BED_SURF={changed}")
    note = (
        "! BED-only HRRPUA upper-bound sensitivity; baseline physics otherwise unchanged.\n"
        "! BED HRRPUA: 180 -> 790 kW/m2; Q=400 J/cm2, W=100 kt, az=270, el=15.\n"
    )
    new_fds.write_text(note + text, encoding="utf-8")

    summary_path = OUTPUT / "case_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.update(
        case=CASE_NAME,
        purpose="BED_only_HRRPUA_upper_bound_sensitivity",
        adaptive_variant=True,
        source_case=SOURCE_NAME,
        changed_factor="BED_HRRPUA_only",
        BED_HRRPUA_baseline_kW_m2=180.0,
        BED_HRRPUA_variant_kW_m2=BED_HRRPUA_KW_M2,
        BED_surface_blocks_changed=changed,
        source_note=(
            "Nylon-6 cone-calorimeter upper-bound sensitivity at 35 kW/m2; "
            "use only as a bounding case pending specimen-specific mattress data"
        ),
        materials_changed=True,
        damage_thresholds_changed=False,
    )
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return OUTPUT


if __name__ == "__main__":
    print(build())

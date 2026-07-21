#!/usr/bin/env python3
"""Build same-Q adaptive cases without modifying the v5 baseline cases."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import build_cases as B
import build_q100_normalized_case as QN


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "cases_adaptive"
BASE = ROOT / "cases_exploratory" / QN.CASE_NAME

ANGLE_CASE = "Q0100_W0100_az090_el75_H1H7_v5_Qnorm_adapt_angle"
HRR_CASE = "Q0100_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRmax"
BA_CASE = "Q0100_W0100_az270_el15_H1H7_v5_Qnorm_adapt_BA"

# Upper-bound sensitivity values selected from measured cone-calorimeter peaks.
# They are not replacements for specimen-specific qualification data.
HRR_LIMITS = {
    "NLZW_BED": 790.0,   # neat Nylon-6, 35 kW/m2 exposure
    "NLZW_CURT": 324.0,  # transportation privacy-curtain fabric
    "JAZPM": 860.0,      # uncoated aircraft-cabin PU foam
    "PVCSL": 259.0,      # PVC panel, 50 kW/m2 exposure
    "CRXJ": 458.0,       # chloroprene seat-support diaphragm
}

HRR_SOURCES = {
    "NLZW_BED": "Polymer 47 (2006), neat Nylon-6 cone test at 35 kW/m2, peak 790 kW/m2",
    "NLZW_CURT": "NIST transportation-material cone table, privacy curtain, maximum peak 324 kW/m2",
    "JAZPM": "Aircraft-cabin raw PU cone study, peak 859.9 kW/m2, rounded to 860",
    "PVCSL": "IAFSS PVC cone tests at 50 kW/m2, maximum peak 259 kW/m2",
    "CRXJ": "NIST transportation-material cone table, chloroprene diaphragm, maximum peak 458 kW/m2",
}


def copy_baseline(case_name: str) -> tuple[Path, Path]:
    case_dir = OUT / case_name
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    for name in (f"{QN.CASE_NAME}.fds", "monitor_registry.json", "flux_faces.csv", "case_summary.json"):
        shutil.copy2(BASE / name, case_dir / name)
    old_fds = case_dir / f"{QN.CASE_NAME}.fds"
    new_fds = case_dir / f"{case_name}.fds"
    old_fds.replace(new_fds)
    text = new_fds.read_text(encoding="utf-8", errors="replace")
    text = re.sub(
        r"(&HEAD\b[^/]*CHID\s*=\s*')[^']+(')",
        rf"\g<1>{case_name}\g<2>", text, count=1, flags=re.I,
    )
    new_fds.write_text(text, encoding="utf-8")
    return case_dir, new_fds


def update_summary(case_dir: Path, case_name: str, **fields) -> None:
    path = case_dir / "case_summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    summary.update(case=case_name, adaptive_variant=True, source_case=QN.CASE_NAME, **fields)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def replace_hrrpua(text: str) -> tuple[str, dict[str, int]]:
    counts = {key: 0 for key in HRR_LIMITS}

    def edit(block_match: re.Match[str]) -> str:
        block = block_match.group(0)
        material = re.search(r"MATL_ID\(1,1\)='([^']+)'", block)
        if not material or "HRRPUA" not in block:
            return block
        key = material.group(1)
        if key == "NLZW":
            thickness = re.search(r"THICKNESS\(1\)=([-+0-9.Ee]+)", block)
            if not thickness:
                return block
            key = "NLZW_BED" if float(thickness.group(1)) > 0.05 else "NLZW_CURT"
        if key not in HRR_LIMITS:
            return block
        block, changed = re.subn(
            r"(HRRPUA\s*=\s*)[-+0-9.Ee]+", rf"\g<1>{HRR_LIMITS[key]:.1f}", block, count=1
        )
        counts[key] += changed
        return block

    return re.sub(r"&SURF\b[\s\S]*?/", edit, text, flags=re.I), counts


def set_combustible_burn_away(text: str) -> tuple[str, dict[str, int]]:
    materials = {"NLZW", "JAZPM", "PVCSL", "CRXJ"}
    counts = {key: 0 for key in materials}

    def edit(block_match: re.Match[str]) -> str:
        block = block_match.group(0)
        material = re.search(r"MATL_ID\(1,1\)='([^']+)'", block)
        if not material or material.group(1) not in materials:
            return block
        key = material.group(1)
        if re.search(r"BURN_AWAY\s*=", block, flags=re.I):
            block, changed = re.subn(
                r"BURN_AWAY\s*=\s*\.(?:TRUE|FALSE)\.", "BURN_AWAY=.TRUE.", block,
                count=1, flags=re.I,
            )
        else:
            block = block.rstrip().rstrip("/") + ", BURN_AWAY=.TRUE./"
            changed = 1
        counts[key] += changed
        return block

    return re.sub(r"&SURF\b[\s\S]*?/", edit, text, flags=re.I), counts


def build_angle() -> dict:
    old_out, old_name = QN.OUT, QN.CASE_NAME
    old_az, old_el = B.CONFIG["azimuth_deg"], B.CONFIG["elevation_deg"]
    try:
        QN.OUT, QN.CASE_NAME = OUT, ANGLE_CASE
        B.CONFIG["azimuth_deg"], B.CONFIG["elevation_deg"] = 90.0, 75.0
        QN.main()
    finally:
        QN.OUT, QN.CASE_NAME = old_out, old_name
        B.CONFIG["azimuth_deg"], B.CONFIG["elevation_deg"] = old_az, old_el
    case_dir = OUT / ANGLE_CASE
    update_summary(
        case_dir, ANGLE_CASE, purpose="same_Q_DDA_angle_sensitivity",
        azimuth_deg=90.0, elevation_deg=75.0, mpi=20,
        changed_factor="incident_angle_only", materials_changed=False,
    )
    return json.loads((case_dir / "case_summary.json").read_text(encoding="utf-8"))


def build_hrr() -> dict:
    case_dir, fds = copy_baseline(HRR_CASE)
    text, counts = replace_hrrpua(fds.read_text(encoding="utf-8", errors="replace"))
    fds.write_text(
        "! Adaptive upper-bound HRRPUA sensitivity; Q, angle and damage criteria unchanged.\n" + text,
        encoding="utf-8",
    )
    update_summary(
        case_dir, HRR_CASE, purpose="same_Q_measured_peak_HRRPUA_sensitivity",
        mpi=20, changed_factor="HRRPUA_only", materials_changed=True,
        hrrpua_kw_m2=HRR_LIMITS, modified_surface_blocks=counts,
        hrrpua_sources=HRR_SOURCES,
    )
    return json.loads((case_dir / "case_summary.json").read_text(encoding="utf-8"))


def build_ba() -> dict:
    case_dir, fds = copy_baseline(BA_CASE)
    text, counts = set_combustible_burn_away(fds.read_text(encoding="utf-8", errors="replace"))
    fds.write_text(
        "! Adaptive BURN_AWAY sensitivity on combustible surfaces only; Q unchanged.\n" + text,
        encoding="utf-8",
    )
    update_summary(
        case_dir, BA_CASE, purpose="same_Q_combustible_BURN_AWAY_sensitivity",
        mpi=20, changed_factor="BURN_AWAY_only", burn_away=True,
        burn_away_materials=sorted(counts), modified_surface_blocks=counts,
    )
    return json.loads((case_dir / "case_summary.json").read_text(encoding="utf-8"))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    summaries = [build_angle(), build_hrr(), build_ba()]
    manifest = {
        "Q_J_cm2": 100.0,
        "run_order": [ANGLE_CASE, HRR_CASE, BA_CASE],
        "single_factor_variants": True,
        "cases": summaries,
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

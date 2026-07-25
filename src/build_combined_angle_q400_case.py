#!/usr/bin/env python3
"""Build the bounded Q400 combined case at the favorable az60/el75 angle."""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import build_cases as B


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases_adaptive"
SOURCE = (
    "Q0400_W0100_az060_el75_H1H7_v5_Qnorm_adapt_"
    "HRRtable_seatSTLfill_thin4mm_v1"
)
COMPARISON = (
    "Q0400_W0100_az270_el15_H1H7_v5_Qnorm_adapt_"
    "combined_SEAT650_BED600_RF040_BAfalse_thin4mm_v1"
)
TARGET = (
    "Q0400_W0100_az060_el75_H1H7_v6_combined_RF040_BA0_shell4"
)
GROUP_HRRPUA = {"SEAT": 650.0, "BED": 600.0, "CURT": 400.0}


def update_group_hrrpua(text: str) -> tuple[str, dict[str, int]]:
    counts = {group: 0 for group in GROUP_HRRPUA}

    def edit(match: re.Match[str]) -> str:
        block = match.group(0)
        surface_id = B.block_id(block)
        group = B.GROUP_BY_SURF.get(surface_id)
        if group is None:
            group = next(
                (
                    candidate
                    for candidate in GROUP_HRRPUA
                    if surface_id.startswith(f"{candidate}_R")
                ),
                None,
            )
        if group not in GROUP_HRRPUA:
            return block
        updated, changed = re.subn(
            r"(HRRPUA\s*=\s*)[-+0-9.Ee]+",
            lambda item: item.group(1) + f"{GROUP_HRRPUA[group]:.1f}",
            block,
            count=1,
            flags=re.I,
        )
        counts[group] += changed
        return updated

    return re.sub(r"&SURF\b.*?/", edit, text, flags=re.S | re.I), counts


def main() -> None:
    source_dir = CASES / SOURCE
    target_dir = CASES / TARGET
    target_dir.mkdir(parents=True, exist_ok=True)

    source_fds = source_dir / f"{SOURCE}.fds"
    text = source_fds.read_text(encoding="utf-8-sig").replace(SOURCE, TARGET)
    text, hrr_counts = update_group_hrrpua(text)
    text, rf_count = re.subn(
        r"(RADIATIVE_FRACTION\s*=\s*)[-+0-9.Ee]+",
        r"\g<1>0.40",
        text,
        count=1,
        flags=re.I,
    )
    if not rf_count:
        raise RuntimeError("RADIATIVE_FRACTION was not found")
    if not all(hrr_counts.values()):
        raise RuntimeError(f"Missing irradiated HRRPUA groups: {hrr_counts}")
    if re.search(r"BURN_AWAY\s*=\s*\.TRUE\.", text, flags=re.I):
        raise RuntimeError("The favorable-angle case must keep BURN_AWAY=.FALSE.")

    note = (
        "! Bounded favorable-angle combined scenario.\n"
        "! Q, yield, materials, ignition temperatures, probes and damage criteria unchanged.\n"
        "! Uses the az60/el75 DDA direction and consistent SEAT/BED/CURT HRRPUA on base and\n"
        "! irradiated surfaces; existing az60 geometry differs by one seat voxel.\n"
    )
    (target_dir / f"{TARGET}.fds").write_text(note + text, encoding="utf-8")
    for filename in ("monitor_registry.json", "flux_faces.csv"):
        source = source_dir / filename
        if source.exists():
            shutil.copy2(source, target_dir / filename)

    summary = json.loads(
        (source_dir / "case_summary.json").read_text(encoding="utf-8")
    )
    summary.update(
        {
            "case": TARGET,
            "created_at": datetime.now().astimezone().isoformat(),
            "source_case": SOURCE,
            "comparison_case": COMPARISON,
            "classification": (
                "bounded favorable-angle combined engineering scenario; "
                "compare separately from fluence threshold cases"
            ),
            "purpose": "test broader DDA exposure with bounded combined combustion inputs",
            "Q_J_cm2": 400.0,
            "yield_kt": 100,
            "azimuth_deg": 60.0,
            "elevation_deg": 75.0,
            "mpi_processes": 32,
            "burn_away": False,
            "radiative_fraction": 0.40,
            "combined_hrrpua_kW_m2": GROUP_HRRPUA,
            "group_surface_replacement_counts": hrr_counts,
            "damage_thresholds_changed": False,
            "physical_rationale": (
                "The completed az60/el75 filled-seat case produced 10/17 severe groups "
                "with lower combustion inputs, versus 5/17 for az270/el15."
            ),
            "known_geometry_delta": (
                "The existing az60 DDA build contains 257 filled seat cells versus "
                "256 in the az270 comparison, a 0.001 m3 difference."
            ),
            "hrrpua_consistency_fix": (
                "SEAT, BED and CURT HRRPUA values are applied to both base and "
                "DDA-irradiated SURF definitions so secondary ignition uses the "
                "same material HRRPUA."
            ),
        }
    )
    (target_dir / "case_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

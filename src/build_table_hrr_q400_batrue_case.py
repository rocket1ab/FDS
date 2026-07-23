#!/usr/bin/env python3
"""Build the paired Q400 material-table HRRPUA case with BURN_AWAY enabled."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "Q0400_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRtable_thickness_audit_v1"
TARGET = "Q0400_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRtable_thickness_audit_BAtrue_v1"


def enable_combustible_burnaway(match: re.Match[str]) -> str:
    block = match.group(0)
    if not re.search(r"\bHRRPUA\s*=\s*(?!0(?:\.0*)?(?:[,/\s]|$))[-+0-9.Ee]+", block, re.I):
        return block
    if re.search(r"\bBURN_AWAY\s*=", block, re.I):
        return re.sub(
            r"\bBURN_AWAY\s*=\s*\.(?:TRUE|FALSE)\.",
            "BURN_AWAY=.TRUE.",
            block,
            flags=re.I,
        )
    return re.sub(r"\s*/\s*$", ", BURN_AWAY=.TRUE. /", block)


def add_required_obstacle_density(text: str) -> tuple[str, int, int]:
    material_density = {}
    for block in re.findall(r"&MATL\b[\s\S]*?/", text, re.I):
        material = re.search(r"\bID\s*=\s*'([^']+)'", block, re.I)
        density = re.search(r"\bDENSITY\s*=\s*([-+0-9.Ee]+)", block, re.I)
        if material and density:
            material_density[material.group(1)] = float(density.group(1))

    burnaway_surfaces = {}
    for block in re.findall(r"&SURF\b[\s\S]*?/", text, re.I):
        if not re.search(r"\bBURN_AWAY\s*=\s*\.TRUE\.", block, re.I):
            continue
        surface = re.search(r"\bID\s*=\s*'([^']+)'", block, re.I)
        material = re.search(r"\bMATL_ID\(1,1\)\s*=\s*'([^']+)'", block, re.I)
        if surface and material and material.group(1) in material_density:
            burnaway_surfaces[surface.group(1)] = material_density[material.group(1)]

    expanded = 0
    density_added = 0

    def update_obstacle(match: re.Match[str]) -> str:
        nonlocal expanded, density_added
        block = match.group(0)
        surface_ids = re.findall(r"'([^']+)'", block)
        densities = [burnaway_surfaces[name] for name in surface_ids if name in burnaway_surfaces]
        if not densities:
            return block
        xb_match = re.search(r"\bXB\s*=\s*([-+0-9.Ee,\s]+)", block, re.I)
        if not xb_match:
            return block
        xb = [
            float(value) for value in re.findall(
                r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?",
                xb_match.group(1),
            )
        ]
        if len(xb) != 6:
            return block
        for axis in range(3):
            low, high = xb[2 * axis], xb[2 * axis + 1]
            if abs(high - low) < 1.0e-9:
                xb[2 * axis] = low - 0.005
                xb[2 * axis + 1] = high + 0.005
                expanded += 1
        replacement = ",".join(f"{value:.6f}" for value in xb) + ", "
        block = block[:xb_match.start(1)] + replacement + block[xb_match.end(1):]
        if not re.search(r"\bBULK_DENSITY\s*=", block, re.I):
            block = re.sub(
                r"\s*/\s*$",
                f", BULK_DENSITY={densities[0]:.1f} /",
                block,
            )
            density_added += 1
        return block

    text = re.sub(r"&OBST\b[\s\S]*?/", update_obstacle, text, flags=re.I)
    return text, density_added, expanded


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
    text = re.sub(r"&SURF\b[\s\S]*?/", enable_combustible_burnaway, text, flags=re.I)
    text, obstacle_density_count, expanded_zero_dimensions = add_required_obstacle_density(text)
    note = (
        "! Q400 paired BURN_AWAY sensitivity case using material-table HRRPUA values.\n"
        "! Only BURN_AWAY changed from the table-HRRPUA Q400 control; it is enabled\n"
        "! only on combustible SURFs with positive HRRPUA. All strict criteria remain unchanged.\n"
    )
    (target / f"{TARGET}.fds").write_text(note + text, encoding="utf-8")

    summary = json.loads((source / "case_summary.json").read_text(encoding="utf-8"))
    summary.update(
        case=TARGET,
        mpi=32,
        purpose="Q400_material_table_HRRPUA_BURN_AWAY_sensitivity",
        source_case=SOURCE,
        changed_factor="BURN_AWAY_false_to_true_only",
        burn_away=True,
        burn_away_changed=True,
        burn_away_scope="combustible_SURFs_with_positive_HRRPUA_only",
        burnaway_obstacles_with_bulk_density=obstacle_density_count,
        burnaway_zero_dimensions_expanded=expanded_zero_dimensions,
        burnaway_minimum_obstacle_thickness_m=0.01,
        probes_changed=False,
        probe_missing_value_policy=(
            "retain finite wall-temperature history and peak; report trailing probe "
            "dropout as possible surface disappearance; never fill missing values with zero"
        ),
        burnaway_evidence_policy=(
            "surface disappearance is supporting evidence only and does not replace "
            "the strict PDF temperature-duration criteria"
        ),
        geometry_changed=False,
        thickness_changed=False,
        ignition_temperature_changed=False,
        damage_thresholds_changed=False,
    )
    (target / "case_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(target)


if __name__ == "__main__":
    main()

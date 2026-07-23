#!/usr/bin/env python3
"""Build a Q400 BURN_AWAY case without expanding zero-volume voxel faces."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "Q0400_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRtable_thickness_audit_v1"
TARGET = "Q0400_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRtable_thickness_audit_BAtrue_v2_volumetric"


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

    densities = {}
    for block in re.findall(r"&MATL\b[\s\S]*?/", text, re.I):
        material = re.search(r"\bID\s*=\s*'([^']+)'", block, re.I)
        density = re.search(r"\bDENSITY\s*=\s*([-+0-9.Ee]+)", block, re.I)
        if material and density:
            densities[material.group(1)] = float(density.group(1))

    ba_surfaces = {}
    duplicate_blocks = []
    for block in re.findall(r"&SURF\b[\s\S]*?/", text, re.I):
        hrr = re.search(r"\bHRRPUA\s*=\s*([-+0-9.Ee]+)", block, re.I)
        surface = re.search(r"\bID\s*=\s*'([^']+)'", block, re.I)
        material = re.search(r"\bMATL_ID\(1,1\)\s*=\s*'([^']+)'", block, re.I)
        if not (hrr and surface and material and float(hrr.group(1)) > 0):
            continue
        if material.group(1) not in densities:
            continue
        original_id = surface.group(1)
        ba_id = f"{original_id}_BA"
        duplicate = re.sub(
            r"(\bID\s*=\s*')[^']+(')",
            rf"\g<1>{ba_id}\g<2>",
            block,
            count=1,
            flags=re.I,
        )
        duplicate = re.sub(r"\s*/\s*$", ", BURN_AWAY=.TRUE. /", duplicate)
        duplicate_blocks.append(duplicate)
        ba_surfaces[original_id] = (ba_id, densities[material.group(1)])

    first_obstacle = re.search(r"&OBST\b", text, re.I)
    if not first_obstacle:
        raise ValueError("No OBST records found")
    text = (
        text[:first_obstacle.start()]
        + "\n! BURN_AWAY duplicates for finite-volume combustible obstacles\n"
        + "\n".join(duplicate_blocks)
        + "\n\n"
        + text[first_obstacle.start():]
    )

    converted = 0
    retained_zero_volume = 0

    def update_obstacle(match: re.Match[str]) -> str:
        nonlocal converted, retained_zero_volume
        block = match.group(0)
        ids = re.findall(r"'([^']+)'", block)
        candidates = [name for name in ids if name in ba_surfaces]
        if not candidates:
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
        if any(abs(xb[2 * axis + 1] - xb[2 * axis]) < 1.0e-9 for axis in range(3)):
            retained_zero_volume += 1
            return block
        density = ba_surfaces[candidates[0]][1]
        for original_id in candidates:
            ba_id = ba_surfaces[original_id][0]
            block = block.replace(f"'{original_id}'", f"'{ba_id}'")
        if not re.search(r"\bBULK_DENSITY\s*=", block, re.I):
            block = re.sub(r"\s*/\s*$", f", BULK_DENSITY={density:.1f} /", block)
        converted += 1
        return block

    text = re.sub(r"&OBST\b[\s\S]*?/", update_obstacle, text, flags=re.I)
    note = (
        "! Q400 BURN_AWAY v2: only finite-volume combustible OBST records use BA SURFs.\n"
        "! Zero-volume voxel faces retain the non-BA control SURFs; geometry is unchanged.\n"
    )
    clean_text = "\n".join(line.rstrip() for line in (note + text).splitlines()) + "\n"
    (target / f"{TARGET}.fds").write_text(clean_text, encoding="utf-8")

    summary = json.loads((source / "case_summary.json").read_text(encoding="utf-8"))
    summary.update(
        case=TARGET,
        mpi=32,
        purpose="Q400_material_table_HRRPUA_BURN_AWAY_finite_volume_sensitivity",
        source_case=SOURCE,
        changed_factor="BURN_AWAY_true_on_finite_volume_combustible_OBST_only",
        burn_away=True,
        burn_away_changed=True,
        burn_away_scope="finite_volume_combustible_OBST_only",
        burnaway_surface_duplicates=len(duplicate_blocks),
        burnaway_obstacles_with_bulk_density=converted,
        zero_volume_combustible_obstacles_retained_non_burnaway=retained_zero_volume,
        geometry_changed=False,
        probes_changed=False,
        damage_thresholds_changed=False,
        probe_missing_value_policy=(
            "retain finite wall-temperature history and last valid time; never fill "
            "missing values with zero"
        ),
    )
    (target / "case_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "target": str(target),
        "ba_surface_duplicates": len(duplicate_blocks),
        "finite_volume_ba_obstacles": converted,
        "zero_volume_retained": retained_zero_volume,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

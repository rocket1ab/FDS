#!/usr/bin/env python3
"""Build the full J/cm2-normalized H1-H7 fluence campaign."""
from __future__ import annotations

import csv
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

import build_cases as B
import build_legacy_stable_cases as L
import build_q100_normalized_case as QN
import voxel_core as V


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "cases_qnorm"
FLUENCES = (50, 100, 200, 300, 400)
BASE_E0_KW_M2 = 1287.0


def build_one(q: int, base: str, parsed: dict, obstacles: list[dict], records: list[dict], integral_s: float) -> dict:
    source_name = f"Q{q:04d}_W0100_az270_el15_H1H7_v2"
    case_name = f"Q{q:04d}_W0100_az270_el15_H1H7_v5_Qnorm"
    source_dir = ROOT / "cases" / source_name
    case_dir = OUT / case_name
    case_dir.mkdir(parents=True, exist_ok=True)
    text = (source_dir / f"{source_name}.fds").read_text(encoding="utf-8", errors="replace")
    text, removed_vents = re.subn(r"&VENT\s+ID='VF\d+'[\s\S]*?/\s*", "", text, flags=re.I)
    text, removed_variants = re.subn(r"&SURF\s+ID='[^']+_R\d+'[\s\S]*?/\s*", "", text, flags=re.I)

    plane_e0 = q * 10.0 / integral_s
    scale = plane_e0 / BASE_E0_KW_M2
    by_obstacle = defaultdict(list)
    for record in records:
        by_obstacle[record["obst"]["idx"]].append(record)

    all_variants = set()
    split_count = 0
    generated_obsts = 0
    flux_rows = []
    for obstacle in obstacles:
        obstacle_records = by_obstacle.get(obstacle["idx"])
        if not obstacle_records:
            continue
        lines, variants = L.split_obstacle(obstacle, obstacle_records, scale)
        if obstacle["raw"] not in text:
            raise RuntimeError(f"Could not locate source OBST {obstacle['idx']} in {source_name}")
        text = text.replace(obstacle["raw"], "\n".join(lines), 1)
        all_variants.update(variants)
        split_count += 1
        generated_obsts += len(lines)
        group = B.group_for(obstacle) or ""
        for record in obstacle_records:
            flux = int(round(record["base_flux"] * scale))
            if flux > 0:
                flux_rows.append([
                    len(flux_rows), group, obstacle["obst_id"], obstacle["surf"], record["face"], flux,
                    *[float(value) for value in record["point"]],
                ])

    base_surfaces = {B.block_id(block): block for block in parsed["SURF"]}
    variant_lines = []
    for surface_id, flux in sorted(all_variants, key=lambda item: (item[1], item[0])):
        raw = base_surfaces[surface_id].rstrip().rstrip("/")
        variant_id = f"{B.ABBR[surface_id]}_R{flux:04d}"
        raw = re.sub(r"ID='[^']+'", f"ID='{variant_id}'", raw, count=1)
        variant_lines.append(raw + f", EXTERNAL_FLUX={flux}, RAMP_EF='NUCLEAR_RAMP'/")
    text = text.replace("&VENT", "! J/cm2-normalized surface variants\n" + "\n".join(variant_lines) + "\n&VENT", 1)
    text = re.sub(
        r"(&HEAD\b[^/]*CHID\s*=\s*')[^']+(')", rf"\g<1>{case_name}\g<2>", text, count=1, flags=re.I
    )
    text = re.sub(r"(T_END\s*=\s*)[-+\d.E]+", r"\g<1>1500.0", text, count=1, flags=re.I)
    text = re.sub(r"(RADIATIVE_FRACTION\s*=\s*)[-+\d.E]+", r"\g<1>0.40", text, count=1, flags=re.I)
    text = L.add_clip(text)
    note = (
        f"! v5_Qnorm: Q={q} J/cm2 normalized at the incident plane.\n"
        "! Geometry, materials, damage thresholds, angle and pulse shape are unchanged.\n"
        f"! E0={plane_e0:.3f} kW/m2; integral(NUCLEAR_RAMP)={integral_s:.6f} s.\n"
    )
    (case_dir / f"{case_name}.fds").write_text(note + text, encoding="utf-8")
    shutil.copy2(source_dir / "monitor_registry.json", case_dir / "monitor_registry.json")
    with (case_dir / "flux_faces.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["index", "group", "obst_id", "surface", "face", "external_flux_kw_m2", "x", "y", "z"])
        writer.writerows(flux_rows)
    max_flux = max(row[5] for row in flux_rows)
    summary = {
        "case": case_name, "purpose": "corrected_incident_plane_fluence_normalization",
        "Q_J_cm2": q, "yield_kt": 100, "azimuth_deg": 270, "elevation_deg": 15,
        "t_end_s": 1500, "mpi": 32, "burn_away": False,
        "nuclear_ramp_integral_s": integral_s, "plane_peak_irradiance_kw_m2": plane_e0,
        "max_local_external_flux_kw_m2": max_flux,
        "max_local_fluence_J_cm2": max_flux * integral_s * 0.1,
        "removed_overlay_vents": removed_vents, "removed_old_surface_variants": removed_variants,
        "domain_vents": 2, "split_source_obstacles": split_count,
        "generated_flux_obstacles": generated_obsts, "flux_surface_variants_used": len(all_variants),
        "materials_changed": False, "damage_thresholds_changed": False,
    }
    (case_dir / "case_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    OUT.mkdir(exist_ok=True)
    base = B.prepare_physics_base()
    parsed, obstacles = B.parse_geometry(base)
    records = B.build_geometry_records(obstacles, V.get_mesh_domain(parsed))
    integral_s = QN.ramp_integral(base)
    summaries = [build_one(q, base, parsed, obstacles, records, integral_s) for q in FLUENCES]
    manifest = {"version": "v5_Qnorm", "fluence_unit": "J/cm2", "cases": summaries}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

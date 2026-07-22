#!/usr/bin/env python3
"""Build a Q-normalized angle variant of the audited HRRPUA campaign."""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

import build_cases as B
import build_hrrpua_upper_campaign as H
import build_legacy_stable_cases as L
import build_q100_normalized_case as QN
import voxel_core as V


ROOT = Path(__file__).resolve().parents[1]
BASE_E0_KW_M2 = 1287.0


def build(q: int, azimuth: float, elevation: float) -> Path:
    angle_tag = f"az{int(azimuth):03d}_el{int(elevation):02d}"
    source_name = f"Q{q:04d}_W0100_az270_el15_H1H7_v2"
    baseline_name = f"Q{q:04d}_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRupper_thickness_audit"
    case_name = f"Q{q:04d}_W0100_{angle_tag}_H1H7_v5_Qnorm_adapt_HRRupper_thickness_audit_angle"
    source_dir = ROOT / "cases" / source_name
    case_dir = ROOT / "cases_adaptive" / case_name
    if not source_dir.is_dir():
        raise FileNotFoundError(source_dir)
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)

    old_az, old_el = B.CONFIG["azimuth_deg"], B.CONFIG["elevation_deg"]
    try:
        B.CONFIG["azimuth_deg"] = azimuth
        B.CONFIG["elevation_deg"] = elevation
        base = B.prepare_physics_base()
        parsed, obstacles = B.parse_geometry(base)
        records = B.build_geometry_records(obstacles, V.get_mesh_domain(parsed))
    finally:
        B.CONFIG["azimuth_deg"], B.CONFIG["elevation_deg"] = old_az, old_el

    integral_s = QN.ramp_integral(base)
    plane_e0 = q * 10.0 / integral_s
    scale = plane_e0 / BASE_E0_KW_M2
    text = (source_dir / f"{source_name}.fds").read_text(encoding="utf-8", errors="replace")
    text, removed_vents = re.subn(r"&VENT\s+ID='VF\d+'[\s\S]*?/\s*", "", text, flags=re.I)
    text, removed_variants = re.subn(r"&SURF\s+ID='[^']+_R\d+'[\s\S]*?/\s*", "", text, flags=re.I)

    by_obstacle: dict[int, list[dict]] = defaultdict(list)
    for record in records:
        by_obstacle[record["obst"]["idx"]].append(record)
    all_variants: set[tuple[str, int]] = set()
    flux_rows: list[list] = []
    split_count = generated_obsts = 0
    for obstacle in obstacles:
        obstacle_records = by_obstacle.get(obstacle["idx"])
        if not obstacle_records:
            continue
        lines, variants = L.split_obstacle(obstacle, obstacle_records, scale)
        if obstacle["raw"] not in text:
            raise RuntimeError(f"Could not locate source OBST {obstacle['idx']}")
        text = text.replace(obstacle["raw"], "\n".join(lines), 1)
        all_variants.update(variants)
        split_count += 1
        generated_obsts += len(lines)
        group = B.group_for(obstacle) or ""
        for record in obstacle_records:
            flux = int(round(record["base_flux"] * scale))
            if flux > 0:
                flux_rows.append([
                    len(flux_rows), group, obstacle["obst_id"], obstacle["surf"],
                    record["face"], flux, *[float(v) for v in record["point"]],
                ])

    base_surfaces = {B.block_id(block): block for block in parsed["SURF"]}
    variant_lines = []
    for surface_id, flux in sorted(all_variants, key=lambda item: (item[1], item[0])):
        raw = base_surfaces[surface_id].rstrip().rstrip("/")
        variant_id = f"{B.ABBR[surface_id]}_R{flux:04d}"
        raw = re.sub(r"ID='[^']+'", f"ID='{variant_id}'", raw, count=1)
        variant_lines.append(raw + f", EXTERNAL_FLUX={flux}, RAMP_EF='NUCLEAR_RAMP'/")
    text = text.replace(
        "&VENT", "! Fixed-Q angle-variant surface definitions\n" + "\n".join(variant_lines) + "\n&VENT", 1
    )

    thickness_changes = {key: 0 for key in H.THICKNESS_M}
    hrrpua_changes = {key: 0 for key in H.HRRPUA_KW_M2}

    def edit_surface(match: re.Match[str]) -> str:
        block = match.group(0)
        group = H.classify_surface(block)
        if group in H.THICKNESS_M:
            block, count = re.subn(
                r"(THICKNESS\(1\)\s*=\s*)[-+0-9.Ee]+",
                rf"\g<1>{H.THICKNESS_M[group]:.6g}", block, count=1, flags=re.I,
            )
            thickness_changes[group] += count
        if group in H.HRRPUA_KW_M2:
            block, count = re.subn(
                r"(HRRPUA\s*=\s*)[-+0-9.Ee]+",
                rf"\g<1>{H.HRRPUA_KW_M2[group]:.1f}", block, count=1, flags=re.I,
            )
            hrrpua_changes[group] += count
        return block

    text = re.sub(r"&SURF\b[\s\S]*?/", edit_surface, text, flags=re.I)
    missing_t = [key for key, count in thickness_changes.items() if count == 0]
    missing_h = [key for key, count in hrrpua_changes.items() if count == 0]
    if missing_t or missing_h:
        raise RuntimeError(f"Surface replacement failure: thickness={missing_t}, HRRPUA={missing_h}")

    text = re.sub(
        r"(&HEAD\b[^/]*CHID\s*=\s*')[^']+(')", rf"\g<1>{case_name}\g<2>",
        text, count=1, flags=re.I,
    )
    text = re.sub(r"(T_END\s*=\s*)[-+\d.E]+", r"\g<1>1500.0", text, count=1, flags=re.I)
    text = re.sub(r"(RADIATIVE_FRACTION\s*=\s*)[-+\d.E]+", r"\g<1>0.40", text, count=1, flags=re.I)
    text = L.add_clip(text)
    note = (
        "! Single-factor incident-angle variant of the audited HRRPUA campaign.\n"
        f"! Q={q} J/cm2, W=100 kt, az={azimuth:g}, el={elevation:g}, T_END=1500 s.\n"
        "! Geometry, materials, thicknesses, HRRPUA, ignition, BURN_AWAY, probes and criteria unchanged.\n"
    )
    (case_dir / f"{case_name}.fds").write_text(note + text, encoding="utf-8")
    shutil.copy2(source_dir / "monitor_registry.json", case_dir / "monitor_registry.json")
    with (case_dir / "flux_faces.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["index", "group", "obst_id", "surface", "face", "external_flux_kw_m2", "x", "y", "z"])
        writer.writerows(flux_rows)

    max_flux = max(row[5] for row in flux_rows)
    summary = {
        "case": case_name,
        "purpose": "fixed_Q_incident_angle_sensitivity",
        "adaptive_variant": True,
        "source_case": baseline_name,
        "changed_factor": "incident_angle_only",
        "Q_J_cm2": q,
        "yield_kt": 100,
        "azimuth_deg": azimuth,
        "elevation_deg": elevation,
        "t_end_s": 1500,
        "mpi": 32,
        "burn_away": False,
        "nuclear_ramp_integral_s": integral_s,
        "plane_peak_irradiance_kw_m2": plane_e0,
        "max_local_external_flux_kw_m2": max_flux,
        "max_local_fluence_J_cm2": max_flux * integral_s * 0.1,
        "thickness_m": H.THICKNESS_M,
        "hrrpua_kW_m2": H.HRRPUA_KW_M2,
        "hrrpua_sources": H.SOURCES,
        "removed_overlay_vents": removed_vents,
        "removed_old_surface_variants": removed_variants,
        "split_source_obstacles": split_count,
        "generated_flux_obstacles": generated_obsts,
        "flux_surface_variants_used": len(all_variants),
        "geometry_changed": False,
        "materials_changed": False,
        "damage_thresholds_changed": False,
    }
    (case_dir / "case_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return case_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--q", type=int, required=True)
    parser.add_argument("--azimuth", type=float, required=True)
    parser.add_argument("--elevation", type=float, required=True)
    args = parser.parse_args()
    build(args.q, args.azimuth, args.elevation)


if __name__ == "__main__":
    main()

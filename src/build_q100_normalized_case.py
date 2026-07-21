#!/usr/bin/env python3
"""Build an independent Q=100 J/cm2 case with plane-fluence normalization."""
from __future__ import annotations

import csv
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

import build_cases as B
import build_legacy_stable_cases as L
import voxel_core as V


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "cases_exploratory"
SOURCE_NAME = "Q0100_W0100_az270_el15_H1H7_v2"
CASE_NAME = "Q0100_W0100_az270_el15_H1H7_v5_Qnorm"
Q_J_CM2 = 100.0
BASE_E0_KW_M2 = 1287.0
MPI_PROCESSES = 20


def ramp_integral(text: str) -> float:
    points = [
        (float(t), float(f))
        for t, f in re.findall(
            r"&RAMP\s+ID='NUCLEAR_RAMP',\s*T=([-+0-9.Ee]+),\s*F=([-+0-9.Ee]+)", text
        )
    ]
    if len(points) < 2:
        raise RuntimeError("NUCLEAR_RAMP is missing")
    return sum((f0 + f1) * 0.5 * (t1 - t0) for (t0, f0), (t1, f1) in zip(points, points[1:]))


def aligned_mesh20() -> str:
    """Merge only validated v4 mesh bands so probes and interfaces remain valid."""
    lines = []
    process = 0
    y1 = [(-1.9, -1.0), (-1.0, -0.1), (-0.1, 0.8), (0.8, 1.7)]
    z1 = [(-2.2, -0.2, 20), (-0.2, 2.6, 28)]
    for iy, (y0, y1_hi) in enumerate(y1):
        for iz, (z0, z1_hi, nk) in enumerate(z1):
            lines.append(
                f"&MESH ID='Mesh01_y{iy}_z{iz}', IJK=85,9,{nk}, "
                f"XB=-0.300000,8.200000,{y0:.6f},{y1_hi:.6f},{z0:.6f},{z1_hi:.6f}, "
                f"MPI_PROCESS={process} /"
            )
            process += 1
    y2 = [(-1.9, -1.0), (-1.0, -0.1), (-0.1, 0.8), (0.8, 1.7)]
    z2 = [(-2.2, -0.6), (-0.6, 1.0), (1.0, 2.6)]
    for iy, (y0, y1_hi) in enumerate(y2):
        for iz, (z0, z1_hi) in enumerate(z2):
            lines.append(
                f"&MESH ID='Mesh02_y{iy}_z{iz}', IJK=36,18,32, "
                f"XB=8.200000,10.100000,{y0:.6f},{y1_hi:.6f},{z0:.6f},{z1_hi:.6f}, "
                f"MPI_PROCESS={process} /"
            )
            process += 1
    if process != MPI_PROCESSES:
        raise RuntimeError("Invalid fixed 20-process mesh partition")
    return "\n".join(lines)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    base = B.prepare_physics_base()
    parsed, obstacles = B.parse_geometry(base)
    records = B.build_geometry_records(obstacles, V.get_mesh_domain(parsed))
    integral_s = ramp_integral(base)
    plane_e0 = Q_J_CM2 * 10.0 / integral_s
    scale = plane_e0 / BASE_E0_KW_M2

    source_dir = ROOT / "cases" / SOURCE_NAME
    case_dir = OUT / CASE_NAME
    case_dir.mkdir(parents=True, exist_ok=True)
    text = (source_dir / f"{SOURCE_NAME}.fds").read_text(encoding="utf-8", errors="replace")
    text, removed_vents = re.subn(r"&VENT\s+ID='VF\d+'[\s\S]*?/\s*", "", text, flags=re.I)
    text, removed_variants = re.subn(
        r"&SURF\s+ID='[^']+_R\d+'[\s\S]*?/\s*", "", text, flags=re.I
    )

    text = B.replace_all(text, "MESH", aligned_mesh20())
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
    text = text.replace("&VENT", "! Plane-fluence-normalized surface variants\n" +
                        "\n".join(variant_lines) + "\n&VENT", 1)

    text = re.sub(
        r"(&HEAD\b[^/]*CHID\s*=\s*')[^']+(')", rf"\g<1>{CASE_NAME}\g<2>", text, count=1, flags=re.I
    )
    text = re.sub(r"(T_END\s*=\s*)[-+\d.E]+", r"\g<1>1500.0", text, count=1, flags=re.I)
    text = re.sub(r"(RADIATIVE_FRACTION\s*=\s*)[-+\d.E]+", r"\g<1>0.40", text, count=1, flags=re.I)
    text = L.add_clip(text)
    note = (
        "! v5_Qnorm exploratory case: Q=100 J/cm2 normalized at the incident plane.\n"
        "! Geometry, materials, damage thresholds, angle and pulse shape are unchanged.\n"
        f"! E0={plane_e0:.3f} kW/m2; integral(NUCLEAR_RAMP)={integral_s:.6f} s.\n"
    )
    (case_dir / f"{CASE_NAME}.fds").write_text(note + text, encoding="utf-8")
    shutil.copy2(source_dir / "monitor_registry.json", case_dir / "monitor_registry.json")
    with (case_dir / "flux_faces.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["index", "group", "obst_id", "surface", "face", "external_flux_kw_m2", "x", "y", "z"])
        writer.writerows(flux_rows)
    summary = {
        "case": CASE_NAME,
        "purpose": "corrected_incident_plane_fluence_normalization",
        "Q_J_cm2": Q_J_CM2,
        "yield_kt": 100,
        "azimuth_deg": 270,
        "elevation_deg": 15,
        "t_end_s": 1500,
        "mpi": MPI_PROCESSES,
        "burn_away": False,
        "nuclear_ramp_integral_s": integral_s,
        "plane_peak_irradiance_kw_m2": plane_e0,
        "max_local_external_flux_kw_m2": max(row[5] for row in flux_rows),
        "max_local_fluence_J_cm2": max(row[5] for row in flux_rows) * integral_s * 0.1,
        "removed_overlay_vents": removed_vents,
        "removed_old_surface_variants": removed_variants,
        "domain_vents": 2,
        "split_source_obstacles": split_count,
        "generated_flux_obstacles": generated_obsts,
        "flux_surface_variants_used": len(all_variants),
        "materials_changed": False,
        "damage_thresholds_changed": False,
    }
    (case_dir / "case_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

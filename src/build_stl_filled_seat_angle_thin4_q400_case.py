#!/usr/bin/env python3
"""Build the Q400, az60/el75 case with filled seats and audited 4 mm shells."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import build_cases as B
from build_q100_normalized_case import BASE_E0_KW_M2, ramp_integral
from build_stl_filled_seat_q400_case import (
    apply_table_hrrpua,
    insert_filled_seats,
    remove_buried_probe_faces,
    remove_u06_shells,
    voxelize_stl,
)


ROOT = Path(__file__).resolve().parents[1]
TARGET = "Q0400_W0100_az060_el75_H1H7_v5_Qnorm_adapt_HRRtable_seatSTLfill_thin4mm_v1"
Q_J_CM2 = 400.0
AZIMUTH_DEG = 60.0
ELEVATION_DEG = 75.0
AUDITED_GROUP_THICKNESS_M = {
    "RADM": 0.004,
    "AL2024": 0.004,
    "AL7075": 0.004,
}


def apply_audited_shell_thickness(text: str) -> tuple[str, dict[str, int]]:
    counts = {group: 0 for group in AUDITED_GROUP_THICKNESS_M}

    def replace(match: re.Match[str]) -> str:
        block = match.group(0)
        surface_id = B.block_id(block)
        group = B.GROUP_BY_SURF.get(surface_id)
        if group not in AUDITED_GROUP_THICKNESS_M:
            return block
        thickness = AUDITED_GROUP_THICKNESS_M[group]
        updated, found = re.subn(
            r"\bTHICKNESS(?:\(\d+\))?\s*=\s*[-+0-9.Ee]+",
            f"THICKNESS(1)={thickness:.6f}",
            block,
            count=1,
            flags=re.I,
        )
        if not found:
            updated = block.rstrip().rstrip("/") + f", THICKNESS(1)={thickness:.6f} /"
        counts[group] += 1
        return updated

    return re.sub(r"&SURF\b[\s\S]*?/", replace, text, flags=re.I), counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stl", required=True, type=Path)
    args = parser.parse_args()

    boxes, seat_audit = voxelize_stl(args.stl)
    base = B.prepare_physics_base()
    base, thickness_counts = apply_audited_shell_thickness(base)
    base, removed_shells = remove_u06_shells(base)
    if removed_shells == 0:
        raise RuntimeError("No original U06 shell OBST records were removed")
    base = insert_filled_seats(base, boxes)

    original_azimuth = B.CONFIG["azimuth_deg"]
    original_elevation = B.CONFIG["elevation_deg"]
    B.CONFIG["azimuth_deg"] = AZIMUTH_DEG
    B.CONFIG["elevation_deg"] = ELEVATION_DEG
    try:
        parsed, obstacles = B.parse_geometry(base)
        domain = B.V.get_mesh_domain(parsed)
        records = B.build_geometry_records(obstacles, domain)
    finally:
        B.CONFIG["azimuth_deg"] = original_azimuth
        B.CONFIG["elevation_deg"] = original_elevation

    records, buried_faces_removed = remove_buried_probe_faces(records, obstacles)
    base_max = max((record["base_flux"] for record in records), default=0.0)
    if base_max <= 0:
        raise RuntimeError("DDA mapping produced no illuminated surface")

    integral_s = ramp_integral(base)
    plane_peak_kw_m2 = Q_J_CM2 * 10.0 / integral_s
    flux_scale = plane_peak_kw_m2 / BASE_E0_KW_M2
    summary = B.build_case(
        base,
        parsed,
        records,
        int(Q_J_CM2),
        base_max,
        case_name=TARGET,
        case_root=ROOT / "cases_adaptive",
        flux_scale=flux_scale,
    )
    case_dir = ROOT / "cases_adaptive" / TARGET
    fds_path = case_dir / f"{TARGET}.fds"
    apply_table_hrrpua(fds_path)

    flux_rows = (case_dir / "flux_faces.csv").read_text(
        encoding="utf-8-sig"
    ).splitlines()[1:]
    local_fluxes = [float(row.split(",")[5]) for row in flux_rows if row]
    summary.update(
        purpose="Q400_angle60_75_table_HRRPUA_STL_filled_seats_audited_4mm_shells",
        source_geometry="reference/Separated_merge_20260720.fds",
        Q_J_cm2=Q_J_CM2,
        yield_kt=100,
        azimuth_deg=AZIMUTH_DEG,
        elevation_deg=ELEVATION_DEG,
        nuclear_ramp_integral_s=integral_s,
        plane_peak_irradiance_kw_m2=plane_peak_kw_m2,
        max_local_external_flux_kw_m2=max(local_fluxes, default=0.0),
        max_local_fluence_J_cm2=max(local_fluxes, default=0.0) * integral_s * 0.1,
        flux_normalization="incident_plane_integral",
        changed_factors=[
            "incident_angle_az60_el75",
            "U06_shell_to_STL_interior_voxel_fill",
            "RADM_AL2024_AL7075_thermal_thickness_to_4mm",
        ],
        audited_group_thickness_m=AUDITED_GROUP_THICKNESS_M,
        audited_surface_update_counts=thickness_counts,
        seat_geometry_audit=seat_audit,
        buried_probe_face_records_removed=buried_faces_removed,
        removed_zero_thickness_u06_obst_count=removed_shells,
        burn_away=False,
        damage_thresholds_changed=False,
    )
    (case_dir / "case_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

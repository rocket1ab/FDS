#!/usr/bin/env python3
"""Build a Q400 case with U06 seat interiors voxelized from the source STL."""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import trimesh

import build_cases as B


ROOT = Path(__file__).resolve().parents[1]
TARGET = "Q0400_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRtable_seatSTLfill_v1"
SEAT_SURF = "聚氨酯泡沫"
PITCH = 0.1


def remove_u06_shells(text: str) -> tuple[str, int]:
    pattern = re.compile(r"&OBST\b[\s\S]*?/")
    removed = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal removed
        block = match.group(0)
        if re.search(r"\bID\s*=\s*'U06\.stl'", block, flags=re.I):
            removed += 1
            return ""
        return block

    return pattern.sub(replace, text), removed


def occupied_fds_cells(components: list[trimesh.Trimesh]) -> set[tuple[int, int, int]]:
    """Select Mesh01 cells whose centers are inside any watertight component."""
    origin = np.array([-0.3, -1.9, -2.2])
    lower = np.floor((np.min([part.bounds[0] for part in components], axis=0) - origin) / PITCH).astype(int)
    upper = np.ceil((np.max([part.bounds[1] for part in components], axis=0) - origin) / PITCH).astype(int)
    axes = [np.arange(max(0, lower[i]), min([85, 36, 48][i], upper[i])) for i in range(3)]
    indices = np.array(np.meshgrid(*axes, indexing="ij")).reshape(3, -1).T
    centers = origin + (indices + 0.5) * PITCH
    inside = np.zeros(len(centers), dtype=bool)
    for part in components:
        inside |= part.contains(centers)
    return {tuple(row) for row in indices[inside]}


def merge_x_runs(cells: set[tuple[int, int, int]]) -> list[list[float]]:
    rows: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, j, k in cells:
        rows[(j, k)].append(i)
    origin = np.array([-0.3, -1.9, -2.2])
    boxes: list[list[float]] = []
    for (j, k), xs in sorted(rows.items()):
        ordered = sorted(set(xs))
        start = previous = ordered[0]
        for value in ordered[1:] + [None]:
            if value is not None and value == previous + 1:
                previous = value
                continue
            boxes.append([
                origin[0] + start * PITCH,
                origin[0] + (previous + 1) * PITCH,
                origin[1] + j * PITCH,
                origin[1] + (j + 1) * PITCH,
                origin[2] + k * PITCH,
                origin[2] + (k + 1) * PITCH,
            ])
            if value is not None:
                start = previous = value
    return boxes


def voxelize_stl(stl_path: Path) -> tuple[list[list[float]], dict]:
    mesh = trimesh.load(stl_path, force="mesh", process=True)
    if not isinstance(mesh, trimesh.Trimesh):
        raise RuntimeError("U06 STL did not load as a triangle mesh")
    mesh.apply_scale(0.001)
    components = list(mesh.split(only_watertight=False))
    if not components or any(not part.is_watertight for part in components):
        raise RuntimeError("At least one separated U06 component is not watertight")
    cells = occupied_fds_cells(components)
    boxes = merge_x_runs(cells)
    volume = len(cells) * PITCH ** 3
    return boxes, {
        "stl": str(stl_path),
        "component_count": len(components),
        "all_components_watertight": True,
        "stl_volume_m3": float(sum(abs(part.volume) for part in components)),
        "fds_voxel_pitch_m": PITCH,
        "filled_cell_count": len(cells),
        "merged_obst_count": len(boxes),
        "fds_voxel_volume_m3": volume,
    }


def insert_filled_seats(text: str, boxes: list[list[float]]) -> str:
    lines = ["! U06 finite-volume seat voxels generated from the source STL"]
    for index, xb in enumerate(boxes):
        coords = ",".join(f"{value:.6f}" for value in xb)
        lines.append(
            f"&OBST ID='U06_STL_FILL_{index:04d}', XB={coords}, "
            f"SURF_ID='{SEAT_SURF}' /"
        )
    insertion = "\n".join(lines) + "\n"
    first_obst = re.search(r"&OBST\b", text)
    if not first_obst:
        raise RuntimeError("No OBST insertion point found")
    return text[:first_obst.start()] + insertion + text[first_obst.start():]


def remove_buried_probe_faces(records: list[dict], obsts: list[dict]) -> tuple[list[dict], int]:
    solid_boxes = [
        np.asarray(obst["xb"], dtype=float)
        for obst in obsts
        if all(obst["xb"][2 * axis + 1] - obst["xb"][2 * axis] > 1e-7 for axis in range(3))
    ]
    kept: list[dict] = []
    removed = 0
    for record in records:
        if B.group_for(record["obst"]) is None:
            kept.append(record)
            continue
        point = np.asarray(record["point"], dtype=float)
        buried = any(
            box[0] + 1e-7 < point[0] < box[1] - 1e-7
            and box[2] + 1e-7 < point[1] < box[3] - 1e-7
            and box[4] + 1e-7 < point[2] < box[5] - 1e-7
            for box in solid_boxes
        )
        if buried:
            removed += 1
        else:
            kept.append(record)
    return kept, removed


def apply_table_hrrpua(fds_path: Path) -> None:
    from build_table_hrr_q400_case import update_surface

    text = fds_path.read_text(encoding="utf-8")
    text = re.sub(r"&SURF\b[\s\S]*?/", update_surface, text, flags=re.I)
    fds_path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stl", required=True, type=Path)
    args = parser.parse_args()

    boxes, audit = voxelize_stl(args.stl)
    base = B.prepare_physics_base()
    base, removed = remove_u06_shells(base)
    if removed == 0:
        raise RuntimeError("No original U06 shell OBST records were removed")
    base = insert_filled_seats(base, boxes)

    parsed, obsts = B.parse_geometry(base)
    domain = B.V.get_mesh_domain(parsed)
    records = B.build_geometry_records(obsts, domain)
    records, buried_faces_removed = remove_buried_probe_faces(records, obsts)
    base_max = max((record["base_flux"] for record in records), default=0)
    if base_max <= 0:
        raise RuntimeError("DDA mapping produced no illuminated surface")

    summary = B.build_case(
        base, parsed, records, 400, base_max,
        case_name=TARGET, case_root=ROOT / "cases_adaptive",
    )
    case_dir = ROOT / "cases_adaptive" / TARGET
    apply_table_hrrpua(case_dir / f"{TARGET}.fds")
    summary.update(
        purpose="Q400_material_table_HRRPUA_with_STL_filled_U06_seats",
        source_geometry="reference/Separated_merge_20260720.fds",
        changed_factor="U06_shell_to_STL_interior_voxel_fill",
        geometry_changed=True,
        seat_geometry_audit=audit,
        buried_probe_face_records_removed=buried_faces_removed,
        removed_zero_thickness_u06_obst_count=removed,
        burn_away=False,
        damage_thresholds_changed=False,
    )
    (case_dir / "case_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

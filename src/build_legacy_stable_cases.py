#!/usr/bin/env python3
"""Build H1-H7 cases using the completed legacy OBST/SURF_ID6 flux method."""
from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from itertools import product
from pathlib import Path

import build_cases as B
import voxel_core as V


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "cases_legacy_stable"
FLUENCES = (50, 100, 200, 300, 400)
FACE_INDEX = {"-x": 0, "+x": 1, "-y": 2, "+y": 3, "-z": 4, "+z": 5}


def intervals(values: list[float]) -> list[tuple[float, float]]:
    unique = []
    for value in sorted(values):
        if not unique or abs(value - unique[-1]) > 1.0e-8:
            unique.append(value)
    if len(unique) == 1:
        return [(unique[0], unique[0])]
    return list(zip(unique[:-1], unique[1:]))


def face_flux(cell: list[float], face: str, records: list[dict], scale: float) -> int:
    center = [(cell[0] + cell[1]) / 2, (cell[2] + cell[3]) / 2, (cell[4] + cell[5]) / 2]
    normal_axis = FACE_INDEX[face] // 2
    for record in records:
        if record["face"] != face:
            continue
        bounds = record["sub_xb"]
        if all(
            bounds[2 * axis] - 1.0e-8 <= center[axis] <= bounds[2 * axis + 1] + 1.0e-8
            for axis in range(3) if axis != normal_axis
        ):
            return int(round(record["base_flux"] * scale))
    return 0


def split_obstacle(obst: dict, records: list[dict], scale: float) -> tuple[list[str], set[tuple[str, int]]]:
    xb = obst["xb"]
    cuts = [[xb[0], xb[1]], [xb[2], xb[3]], [xb[4], xb[5]]]
    for record in records:
        sub = record["sub_xb"]
        for axis in range(3):
            cuts[axis].extend((sub[2 * axis], sub[2 * axis + 1]))

    cells = product(intervals(cuts[0]), intervals(cuts[1]), intervals(cuts[2]))
    lines = []
    variants = set()
    base_surf = obst["surf"]
    abbr = B.ABBR[base_surf]
    for ix, iy, iz in cells:
        cell = [ix[0], ix[1], iy[0], iy[1], iz[0], iz[1]]
        faces = [base_surf] * 6
        external = []
        if abs(cell[0] - xb[0]) < 1.0e-8:
            external.append("-x")
        if abs(cell[1] - xb[1]) < 1.0e-8:
            external.append("+x")
        if abs(cell[2] - xb[2]) < 1.0e-8:
            external.append("-y")
        if abs(cell[3] - xb[3]) < 1.0e-8:
            external.append("+y")
        if abs(cell[4] - xb[4]) < 1.0e-8:
            external.append("-z")
        if abs(cell[5] - xb[5]) < 1.0e-8:
            external.append("+z")
        for face in external:
            flux = face_flux(cell, face, records, scale)
            if flux <= 0:
                continue
            variant = f"{abbr}_R{flux:04d}"
            faces[FACE_INDEX[face]] = variant
            variants.add((base_surf, flux))
        coords = ",".join(f"{value:.6f}" for value in cell)
        surf_ids = ",".join(f"'{sid}'" for sid in faces)
        lines.append(f"&OBST XB={coords}, SURF_ID6={surf_ids} /")
    return lines, variants


def add_clip(text: str) -> str:
    if re.search(r"&CLIP\b", text, flags=re.I):
        return text
    return re.sub(
        r"(&HEAD\b[\s\S]*?/)",
        r"\1\n&CLIP MINIMUM_DENSITY=0.01, MAXIMUM_DENSITY=10000/",
        text,
        count=1,
        flags=re.I,
    )


def build_one(q: int, obsts: list[dict], records: list[dict], base_max: float) -> dict:
    source_name = f"Q{q:04d}_W0100_az270_el15_H1H7_v2"
    case_name = f"Q{q:04d}_W0100_az270_el15_H1H7_v4_legacy_stable"
    source_dir = ROOT / "cases" / source_name
    case_dir = OUT / case_name
    case_dir.mkdir(parents=True, exist_ok=True)
    text = (source_dir / f"{source_name}.fds").read_text(encoding="utf-8", errors="replace")

    # Remove only generated illuminated-face overlays. The two original OPEN
    # domain vents remain untouched.
    text, removed_vents = re.subn(r"&VENT\s+ID='VF\d+'[\s\S]*?/\s*", "", text, flags=re.I)
    scale = B.CONFIG["q400_reference_max_external_flux_kw_m2"] / base_max * q / 400.0
    by_obstacle = defaultdict(list)
    for record in records:
        by_obstacle[record["obst"]["idx"]].append(record)

    all_variants = set()
    split_count = 0
    generated_obsts = 0
    for obst in obsts:
        obstacle_records = by_obstacle.get(obst["idx"])
        if not obstacle_records:
            continue
        lines, variants = split_obstacle(obst, obstacle_records, scale)
        if obst["raw"] not in text:
            raise RuntimeError(f"Could not locate source OBST {obst['idx']} in {source_name}")
        text = text.replace(obst["raw"], "\n".join(lines), 1)
        all_variants.update(variants)
        split_count += 1
        generated_obsts += len(lines)

    text = re.sub(
        r"(&HEAD\b[^/]*CHID\s*=\s*')[^']+(')", rf"\g<1>{case_name}\g<2>", text, count=1, flags=re.I
    )
    text = re.sub(r"(T_END\s*=\s*)[-+\d.E]+", r"\g<1>900.0", text, count=1, flags=re.I)
    text, reaction_count = re.subn(
        r"(RADIATIVE_FRACTION\s*=\s*)[-+\d.E]+", r"\g<1>0.40", text, count=1, flags=re.I
    )
    if reaction_count != 1:
        raise RuntimeError(f"Could not set completed-reference radiative fraction in {case_name}")
    text = add_clip(text)
    note = (
        "! v4_legacy_stable: updated H1-H7 geometry with completed legacy OBST/SURF_ID6 flux injection.\n"
        "! The generated VF overlay vents are removed; peak flux and material parameters are unchanged.\n"
        "! Baseline matches completed Q50_W100_el15_BA0_RF40_B1: RF=0.40, CLIP, original Q_RAMP.\n"
    )
    fds_path = case_dir / f"{case_name}.fds"
    fds_path.write_text(note + text, encoding="utf-8")

    for filename in ("monitor_registry.json", "flux_faces.csv"):
        shutil.copy2(source_dir / filename, case_dir / filename)
    summary = json.loads((source_dir / "case_summary.json").read_text(encoding="utf-8"))
    summary.update({
        "case": case_name,
        "t_end_s": 900,
        "stability_version": "v4_legacy_stable",
        "flux_injection": "split_obst_surf_id6",
        "removed_overlay_vents": removed_vents,
        "illuminated_vents": 0,
        "domain_vents": 2,
        "split_source_obstacles": split_count,
        "generated_flux_obstacles": generated_obsts,
        "flux_surface_variants_used": len(all_variants),
        "legacy_reference": "Q50_W100_el15_BA0_RF40_B1",
        "radiative_fraction": 0.40,
        "peak_hrrpua_changed": False,
        "external_flux_changed": False,
    })
    (case_dir / "case_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    OUT.mkdir(exist_ok=True)
    base = B.prepare_physics_base()
    parsed, obsts = B.parse_geometry(base)
    records = B.build_geometry_records(obsts, V.get_mesh_domain(parsed))
    base_max = max(record["base_flux"] for record in records)
    summaries = [build_one(q, obsts, records, base_max) for q in FLUENCES]
    manifest = {
        "version": "v4_legacy_stable",
        "completed_reference": "Q50_W100_el15_BA0_RF40_B1",
        "cases": summaries,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

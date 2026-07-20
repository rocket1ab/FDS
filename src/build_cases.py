#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

import voxel_core as V


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reference" / "Separated_merge_20260720.fds"
PHYSICS = ROOT / "reference" / "Q0400_BA0_coat_T1500_v4.fds"
CASES = ROOT / "cases"
CONFIG = json.loads((ROOT / "config" / "project.json").read_text(encoding="utf-8"))

OLD_SURFS = {
    "E-玻璃纤维", "丙烯酸塑料", "尼龙织物_床垫", "尼龙织物_窗帘3mm",
    "环氧玻璃纤维", "聚氨酯泡沫", "铝合金2024", "铝合金5052",
    "铝合金7075", "铝合金7075_氧气瓶",
}
GROUP_BY_SURF = {
    "E-玻璃纤维": "RADM", "丙烯酸塑料": "WINS",
    "尼龙织物_床垫": "BED", "尼龙织物_窗帘3mm": "CURT",
    "聚氨酯泡沫": "SEAT", "铝合金2024": "AL2024",
    "铝合金5052": "AL5052", "铝合金7075": "AL7075",
    "铝合金7075_氧气瓶": "O2TANK",
    "导航子系统": "H1", "任务子系统": "H2", "显示子系统": "H3",
    "通信子系统": "H4", "电池": "H5", "电力传输子系统": "H6",
    "操纵子系统": "H7",
}
ABBR = {surf: group for surf, group in GROUP_BY_SURF.items()}
ABBR["环氧玻璃纤维"] = "U4"


def blocks(text: str, tag: str) -> list[str]:
    return [m.group(0) for m in re.finditer(rf"&{tag}\b[\s\S]*?/", text)]


def block_id(block: str) -> str | None:
    match = re.search(r"\bID\s*=\s*'([^']+)'", block)
    return match.group(1) if match else None


def replace_all(text: str, tag: str, replacement: str) -> str:
    pattern = re.compile(rf"&{tag}\b[\s\S]*?/")
    matches = list(pattern.finditer(text))
    if not matches:
        raise RuntimeError(f"No {tag} blocks found")
    start, end = matches[0].start(), matches[-1].end()
    return text[:start] + replacement.rstrip() + "\n" + text[end:]


def prepare_physics_base() -> str:
    source = SOURCE.read_text(encoding="utf-8", errors="replace")
    ref = PHYSICS.read_text(encoding="utf-8", errors="replace")

    source = replace_all(source, "REAC", "\n".join(blocks(ref, "REAC")))

    ref_matls = {block_id(b): b for b in blocks(ref, "MATL")}
    extra_matls = [
        "&MATL ID='LHJ6061', SPECIFIC_HEAT=0.896, CONDUCTIVITY=167.0, DENSITY=2700.0, EMISSIVITY=0.9/",
        "&MATL ID='PVCSL', SPECIFIC_HEAT=0.84, CONDUCTIVITY=0.19, DENSITY=1449.0, EMISSIVITY=0.9/",
        "&MATL ID='CRXJ', SPECIFIC_HEAT=1.12, CONDUCTIVITY=0.19, DENSITY=1500.0, EMISSIVITY=0.9/",
    ]
    source = replace_all(source, "MATL", "\n".join(ref_matls.values()) + "\n" + "\n".join(extra_matls))

    ref_surfs = {block_id(b): b for b in blocks(ref, "SURF") if not re.search(r"_R\d+", block_id(b) or "")}
    updated = []
    for surf in blocks(source, "SURF"):
        sid = block_id(surf)
        updated.append(ref_surfs[sid] if sid in OLD_SURFS and sid in ref_surfs else surf)
    source = replace_all(source, "SURF", "\n".join(updated))

    ref_ramps = blocks(ref, "RAMP")
    nuclear = [b for b in ref_ramps if block_id(b) == "NUCLEAR_RAMP"]
    q_ramp = [b for b in ref_ramps if block_id(b) == "Q_RAMP"]
    source = replace_all(source, "RAMP", "\n".join(nuclear + q_ramp))
    source = re.sub(r"&TIME\b[\s\S]*?/", "&TIME T_END=1500.0/", source, count=1)
    source = re.sub(r"&HEAD\b[\s\S]*?/", "&HEAD CHID='aircraft_H1_H7_base'/", source, count=1)

    # H6/H7 use the prescribed ignition-temperature + HRRPUA model.
    def amend_equipment_surf(match: re.Match[str]) -> str:
        raw = match.group(0)
        sid = block_id(raw)
        if sid not in {"电力传输子系统", "操纵子系统"}:
            return raw
        raw = re.sub(r",?\s*RAMP_Q\s*=\s*'[^']+'", "", raw)
        return raw.rstrip("/").rstrip() + ", RAMP_Q='Q_RAMP'/"

    source = re.sub(r"&SURF\b[\s\S]*?/", amend_equipment_surf, source)
    for match in list(re.finditer(r"&SURF\b[\s\S]*?/", source)):
        raw = match.group(0)
        if "EXTERNAL_FLUX" in raw or "RAMP_EF" in raw:
            source = source.replace(raw, V.strip_external_flux(raw), 1)
    return source


def parse_geometry(text: str):
    parsed = defaultdict(list)
    obsts = []
    for match in re.finditer(r"(&\w+[\s\S]*?/)", text):
        raw = match.group(1)
        tag = re.match(r"&(\w+)", raw).group(1)
        if tag != "OBST":
            parsed[tag].append(raw)
            continue
        xb_match = re.search(r"XB=\s*([-\d.E+,\s]+?)(?:,\s*[A-Z]|/)", raw)
        if not xb_match:
            parsed["OBST_OTHER"].append(raw)
            continue
        vals = [float(v.strip()) for v in xb_match.group(1).split(",") if v.strip()][:6]
        sid_match = re.search(r"SURF_ID\s*=\s*'([^']+)'", raw)
        oid_match = re.search(r"\bID\s*=\s*'([^']+)'", raw)
        surf = sid_match.group(1) if sid_match else ""
        obsts.append({
            "xb": vals, "surf": surf, "raw": raw, "comb": surf in V.COMB_SURFS,
            "flux_recv": surf in V.FLUX_RECV_SURFS, "idx": len(obsts),
            "obst_id": oid_match.group(1) if oid_match else "",
        })
    return parsed, obsts


def split_mesh_for_mpi(text: str, ncores: int = 32) -> str:
    meshes = list(re.finditer(
        r"&MESH\b[^/]*?IJK=(\d+),(\d+),(\d+)[^/]*?XB=([-\d.eE+]+),([-\d.eE+]+),"
        r"([-\d.eE+]+),([-\d.eE+]+),([-\d.eE+]+),([-\d.eE+]+)\s*/", text))
    info = []
    for match in meshes:
        ijk = [int(match.group(i)) for i in range(1, 4)]
        xb = [float(match.group(i)) for i in range(4, 10)]
        mid = re.search(r"&MESH\s+ID='([^']*)'", match.group())
        info.append({"ijk": ijk, "xb": xb, "cells": math.prod(ijk),
                     "id": mid.group(1) if mid else "M", "span": match.span()})
    total = sum(item["cells"] for item in info)
    alloc = [max(1, round(ncores * item["cells"] / total)) for item in info]
    while sum(alloc) > ncores:
        i = max(range(len(alloc)), key=alloc.__getitem__)
        alloc[i] -= 1
    while sum(alloc) < ncores:
        i = max(range(len(alloc)), key=alloc.__getitem__)
        alloc[i] += 1
    proc = 0
    replacements = []
    for item, count in zip(info, alloc):
        i, j, k = item["ijk"]
        xb = item["xb"]
        axis = max(range(3), key=lambda n: item["ijk"][n])
        cells = item["ijk"][axis]
        base, rem = divmod(cells, count)
        counts = [base + (n < rem) for n in range(count)]
        lo, hi = (xb[0], xb[1]) if axis == 0 else ((xb[2], xb[3]) if axis == 1 else (xb[4], xb[5]))
        delta = (hi - lo) / cells
        offset = 0
        lines = []
        for ncell in counts:
            bounds = list(xb)
            bounds[2 * axis] = lo + offset * delta
            bounds[2 * axis + 1] = lo + (offset + ncell) * delta
            dims = [i, j, k]
            dims[axis] = ncell
            lines.append(
                f"&MESH ID='{item['id']}_{proc}', IJK={dims[0]},{dims[1]},{dims[2]}, "
                f"XB={','.join(f'{v:.6f}' for v in bounds)}, MPI_PROCESS={proc} /"
            )
            offset += ncell
            proc += 1
        replacements.append((*item["span"], "\n".join(lines)))
    for start, end, replacement in sorted(replacements, reverse=True):
        text = text[:start] + replacement + text[end:]
    if proc != ncores:
        raise RuntimeError(f"Expected {ncores} MPI meshes, generated {proc}")
    return text


def face_point(xb, face: str, offset: float = 0.005):
    point = np.array([(xb[0] + xb[1]) / 2, (xb[2] + xb[3]) / 2, (xb[4] + xb[5]) / 2])
    point += V.FN[face] * offset
    ior = {"-x": -1, "+x": 1, "-y": -2, "+y": 2, "-z": -3, "+z": 3}[face]
    return point, ior


def vent_plane(xb, face: str):
    """Collapse a voxel sub-patch onto its actual OBST boundary plane."""
    plane = list(xb)
    if face == "-x":
        plane[1] = plane[0]
    elif face == "+x":
        plane[0] = plane[1]
    elif face == "-y":
        plane[3] = plane[2]
    elif face == "+y":
        plane[2] = plane[3]
    elif face == "-z":
        plane[5] = plane[4]
    elif face == "+z":
        plane[4] = plane[5]
    else:
        raise ValueError(f"Unknown face: {face}")
    return plane


def group_for(obst: dict) -> str | None:
    oid = obst["obst_id"]
    if oid == "U4.stl" and obst["surf"] == "环氧玻璃纤维":
        return "U4"
    return GROUP_BY_SURF.get(obst["surf"])


def diverse_candidates(records: list[dict], count: int) -> list[dict]:
    if len(records) <= count:
        return records
    records = sorted(records, key=lambda r: r["base_flux"], reverse=True)
    chosen = [records[0]]
    remaining = records[1:]
    while remaining and len(chosen) < count:
        def score(candidate):
            p = candidate["point"]
            distance = min(float(np.linalg.norm(p - item["point"])) for item in chosen)
            flux_bonus = candidate["base_flux"] / max(records[0]["base_flux"], 1.0)
            return distance + 0.4 * flux_bonus
        best = max(remaining, key=score)
        chosen.append(best)
        remaining.remove(best)
    return chosen


def build_geometry_records(obsts, domain):
    opaque, glass, grid = V.build_voxel_grids(obsts, domain)
    direction = V.sun_vec(CONFIG["azimuth_deg"], CONFIG["elevation_deg"])
    records = []
    for obst in obsts:
        if not obst["flux_recv"]:
            continue
        for sub_xb, face, flux in V.compute_obst_flux(obst, direction, 1287.0, opaque, glass, grid):
            point, ior = face_point(sub_xb, face)
            records.append({"obst": obst, "sub_xb": sub_xb, "face": face,
                            "base_flux": float(flux), "point": point, "ior": ior})
    return records


def build_case(base: str, parsed, records: list[dict], q: int, base_max: float):
    case_name = f"Q{q:04d}_W0100_az270_el15_H1H7_v2"
    case_dir = CASES / case_name
    case_dir.mkdir(parents=True, exist_ok=True)
    scale = CONFIG["q400_reference_max_external_flux_kw_m2"] / base_max * q / 400.0
    surf_raw = {block_id(b): b for b in parsed["SURF"]}
    variants = {}
    vents = []
    candidates = defaultdict(list)
    flux_rows = []
    for index, record in enumerate(records):
        obst = record["obst"]
        group = group_for(obst)
        flux = int(round(record["base_flux"] * scale))
        if group:
            candidate = dict(record)
            candidate["group"] = group
            candidates[group].append(candidate)
        if flux <= 0:
            continue
        sid = obst["surf"]
        variant = f"{ABBR[sid]}_R{flux:04d}"
        variants[variant] = (sid, flux)
        xb = ",".join(f"{v:.6f}" for v in vent_plane(record["sub_xb"], record["face"]))
        vents.append(f"&VENT ID='VF{index:05d}', XB={xb}, SURF_ID='{variant}' /")
        flux_rows.append([index, group or "", obst["obst_id"], sid, record["face"], flux, *record["point"]])

    variant_lines = []
    for variant, (sid, flux) in sorted(variants.items(), key=lambda item: (item[1][1], item[0])):
        raw = surf_raw[sid].rstrip().rstrip("/")
        raw = re.sub(r"ID='[^']+'", f"ID='{variant}'", raw, count=1)
        variant_lines.append(raw + f", EXTERNAL_FLUX={flux}, RAMP_EF='NUCLEAR_RAMP'/")

    probe_lines = []
    registry = {}
    for group in json.loads((ROOT / "config" / "damage_criteria.json").read_text(encoding="utf-8"))["groups"]:
        limit = CONFIG["h3_probe_candidates"] if group == "H3" else CONFIG["probe_candidates_per_group"]
        selected = diverse_candidates(candidates.get(group, []), limit)
        registry[group] = []
        for index, candidate in enumerate(selected):
            x, y, z = candidate["point"]
            ior = candidate["ior"]
            wt = f"P_{group}_{index:02d}_WT"
            hf = f"P_{group}_{index:02d}_HF"
            probe_lines.append(f"&DEVC ID='{wt}', QUANTITY='WALL TEMPERATURE', XYZ={x:.4f},{y:.4f},{z:.4f}, IOR={ior} /")
            probe_lines.append(f"&DEVC ID='{hf}', QUANTITY='NET HEAT FLUX', XYZ={x:.4f},{y:.4f},{z:.4f}, IOR={ior} /")
            registry[group].append({"wt": wt, "hf": hf, "xyz": [round(float(x), 4), round(float(y), 4), round(float(z), 4)],
                                    "ior": ior, "surface": candidate["obst"]["surf"],
                                    "obst_id": candidate["obst"]["obst_id"], "base_flux": candidate["base_flux"]})

    domain = V.get_mesh_domain(parsed)
    x0, x1, y0, y1, z0, z1 = domain
    probe_lines.extend([
        f"&DEVC ID='HRR_total', QUANTITY='HRR', XB={x0+.05:.3f},{x1-.05:.3f},{y0+.05:.3f},{y1-.05:.3f},{z0+.05:.3f},{z1-.05:.3f} /",
        "&SLCF PBY=0.0, QUANTITY='TEMPERATURE' /",
        "&SLCF PBY=0.0, QUANTITY='HRRPUV' /",
        "&SLCF PBZ=0.8, QUANTITY='TEMPERATURE' /",
        "&BNDF QUANTITY='WALL TEMPERATURE' /",
        "&BNDF QUANTITY='NET HEAT FLUX' /",
        "&BNDF QUANTITY='BURNING RATE' /",
    ])

    text = re.sub(r"(&HEAD\b[^/]*CHID=')[^']+(')", rf"\g<1>{case_name}\g<2>", base, count=1)
    injection = "\n! Voxel external-flux surface variants\n" + "\n".join(variant_lines)
    injection += "\n! Voxel illuminated face overlays\n" + "\n".join(vents)
    injection += "\n! Redundant surface probes\n" + "\n".join(probe_lines) + "\n"
    text = text.replace("&TAIL", injection + "&TAIL", 1)
    text = split_mesh_for_mpi(text, CONFIG["mpi_processes"])
    fds_path = case_dir / f"{case_name}.fds"
    fds_path.write_text(text, encoding="utf-8")
    (case_dir / "monitor_registry.json").write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    with (case_dir / "flux_faces.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["index", "group", "obst_id", "surface", "face", "external_flux_kw_m2", "x", "y", "z"])
        writer.writerows(flux_rows)
    summary = {"case": case_name, "Q_J_cm2": q, "yield_kt": 100, "azimuth_deg": 270,
               "elevation_deg": 15, "t_end_s": 1500, "mpi": 32, "burn_away": False,
               "surface_variants": len(variants), "illuminated_vents": len(vents),
               "temperature_probes": sum(len(v) for v in registry.values()),
               "probe_counts": {k: len(v) for k, v in registry.items()},
               "max_external_flux_kw_m2": max((row[5] for row in flux_rows), default=0)}
    (case_dir / "case_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main():
    base = prepare_physics_base()
    parsed, obsts = parse_geometry(base)
    domain = V.get_mesh_domain(parsed)
    records = build_geometry_records(obsts, domain)
    base_max = max((record["base_flux"] for record in records), default=0)
    if base_max <= 0:
        raise RuntimeError("Voxel mapping produced no illuminated surfaces")
    summaries = [build_case(base, parsed, records, int(q), base_max) for q in CONFIG["fluence_J_cm2"]]
    manifest = {"source": str(SOURCE), "physics_reference": str(PHYSICS),
                "base_voxel_max_kw_m2": base_max, "records": len(records), "cases": summaries}
    (ROOT / "case_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

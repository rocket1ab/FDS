#!/usr/bin/env python3
"""Build v6 copies with every surface probe projected onto its intended FDS face."""

from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path

import validate_and_plot_probe_distribution as probe_qa


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "cases_qnorm"
OUTPUT = ROOT / "cases_probe_corrected"
EXCLUDED = json.loads(
    (ROOT / "config" / "excluded_probe_ids_v5.json").read_text(encoding="utf-8")
)["wall_temperature_ids"]
FACE_INDEX = {-1: 0, 1: 1, -2: 2, 2: 3, -3: 4, 3: 5}


def nearest_target_face(xyz, ior: int, group: str, obstacles: list[dict]):
    axis = abs(ior) - 1
    face_index = FACE_INDEX[ior]
    other_axes = [value for value in range(3) if value != axis]
    candidates = []
    for obstacle in obstacles:
        if probe_qa.group_for_surface(obstacle["surfaces"][face_index]) != group:
            continue
        box = obstacle["xb"]
        if not all(box[2 * a] - 0.051 <= xyz[a] <= box[2 * a + 1] + 0.051 for a in other_axes):
            continue
        candidates.append((abs(xyz[axis] - box[face_index]), obstacle))
    if not candidates:
        raise RuntimeError(f"No intended face found for {group} at {xyz}, IOR={ior}")
    return min(candidates, key=lambda item: item[0])


def replace_devc_xyz(text: str, devc_id: str, xyz: list[float], ior: int) -> str:
    pattern = rf"(&DEVC\s+ID='{re.escape(devc_id)}'[\s\S]*?\bXYZ\s*=\s*)[-+0-9.eE]+\s*,\s*[-+0-9.eE]+\s*,\s*[-+0-9.eE]+([\s\S]*?\bIOR\s*=\s*)-?\d+([\s\S]*?/)"
    coords = ",".join(f"{value:.4f}" for value in xyz)
    replacement = rf"\g<1>{coords}\g<2>{ior}\g<3>"
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.I)
    if count != 1:
        raise RuntimeError(f"Could not update {devc_id}")
    return updated


def build_case(source_dir: Path) -> dict:
    old_name = source_dir.name
    new_name = old_name.replace("_v5_Qnorm", "_v6_probe_fixed")
    output_dir = OUTPUT / new_name
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    source_fds = next(source_dir.glob("*.fds"))
    text = source_fds.read_text(encoding="utf-8", errors="replace")
    obstacles = probe_qa.parse_obstacles(text)
    registry = json.loads((source_dir / "monitor_registry.json").read_text(encoding="utf-8"))
    repairs = []

    for group, entries in registry.items():
        for entry in entries:
            if entry["wt"] not in EXCLUDED:
                continue
            old_xyz = [float(value) for value in entry["xyz"]]
            ior = int(entry["ior"])
            distance, obstacle = nearest_target_face(old_xyz, ior, group, obstacles)
            axis = abs(ior) - 1
            sign = 1 if ior > 0 else -1
            new_xyz = old_xyz.copy()
            new_xyz[axis] = obstacle["xb"][FACE_INDEX[ior]] + sign * 0.035
            new_xyz = [round(value, 4) for value in new_xyz]
            for devc_id in (entry["wt"], entry["hf"]):
                text = replace_devc_xyz(text, devc_id, new_xyz, ior)
            entry["xyz"] = new_xyz
            repairs.append({
                "group": group, "wt": entry["wt"], "hf": entry["hf"],
                "old_xyz": old_xyz, "new_xyz": new_xyz, "ior": ior,
                "old_face_distance_m": distance, "new_face_distance_m": 0.035,
            })

    text = re.sub(
        r"(&HEAD\b[^/]*\bCHID\s*=\s*')[^']+(')", rf"\g<1>{new_name}\g<2>", text, count=1, flags=re.I
    )
    note = (
        "! v6_probe_fixed: six QA-failed WT/HF pairs projected onto their intended material faces.\n"
        "! External flux, geometry, materials, pulse, combustion and damage criteria are unchanged.\n"
    )
    (output_dir / f"{new_name}.fds").write_text(note + text, encoding="utf-8")
    (output_dir / "monitor_registry.json").write_text(
        json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    shutil.copy2(source_dir / "flux_faces.csv", output_dir / "flux_faces.csv")
    summary = json.loads((source_dir / "case_summary.json").read_text(encoding="utf-8"))
    summary.update({
        "case": new_name, "probe_version": "v6_probe_fixed", "probe_repairs": len(repairs),
        "boundary_field_wall_temperature": True, "boundary_field_net_heat_flux": True,
        "source_case": old_name,
    })
    (output_dir / "case_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "probe_repairs.json").write_text(
        json.dumps(repairs, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    validation, _, _ = probe_qa.validate(output_dir)
    if not validation["all_positions_valid"]:
        raise RuntimeError(f"Probe repair did not pass QA for {new_name}: {validation['issues']}")
    return {
        "case": new_name, "source": old_name, "repairs": repairs,
        "validated_probes": validation["validated_probe_count"],
        "total_probes": validation["temperature_probe_count"],
    }


def main():
    OUTPUT.mkdir(exist_ok=True)
    sources = sorted(SOURCE.glob("Q*_v5_Qnorm"))
    if not sources:
        raise FileNotFoundError(f"No v5 cases under {SOURCE}")
    results = [build_case(source) for source in sources]
    manifest = {
        "version": "v6_probe_fixed", "source_version": "v5_Qnorm",
        "physics_changed": False, "probe_locations_changed": True,
        "boundary_field_note": "BNDF WALL TEMPERATURE remains the full-surface maximum cross-check",
        "cases": results,
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

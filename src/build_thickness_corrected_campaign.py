#!/usr/bin/env python3
"""Build the Q100-Q400 surface-layer thickness audit campaign."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLUENCES = (100, 200, 300, 400)

# FDS SURF thickness is the one-dimensional material layer, not the OBST depth.
# Values for WINS/CURT/U4/RADM restore the latest PyroSim export. The BED value
# is a conservative upper representative nylon upholstery-fabric thickness.
THICKNESS_M = {
    "RADM": 0.100,
    "WINS": 0.025,
    "BED": 0.00089,
    "CURT": 0.003,
    "U4": 0.006,
}


def surface_group(surface_id: str) -> str | None:
    if surface_id == "E-玻璃纤维" or surface_id.startswith("RADM_R"):
        return "RADM"
    if surface_id == "丙烯酸塑料" or surface_id.startswith("WINS_R"):
        return "WINS"
    if surface_id == "尼龙织物_床垫" or surface_id.startswith("BED_R"):
        return "BED"
    if surface_id.startswith("尼龙织物_窗帘") or surface_id.startswith("CURT_R"):
        return "CURT"
    if surface_id == "环氧玻璃纤维" or surface_id.startswith("U4_R"):
        return "U4"
    return None


def build_one(q: int) -> Path:
    source_name = f"Q{q:04d}_W0100_az270_el15_H1H7_v5_Qnorm"
    # node01 has 20 logical CPUs; its validated Q100 input carries the equivalent
    # 20-way mesh assignment. Q200-Q400 use the 32-way campaign inputs.
    source_root = "cases_exploratory" if q == 100 else "cases_qnorm"
    source = ROOT / source_root / source_name
    case_name = f"{source_name}_adapt_thickness_audit"
    output = ROOT / "cases_adaptive" / case_name
    if not source.is_dir():
        raise FileNotFoundError(source)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for name in (f"{source_name}.fds", "monitor_registry.json", "flux_faces.csv", "case_summary.json"):
        shutil.copy2(source / name, output / name)

    old_fds = output / f"{source_name}.fds"
    new_fds = output / f"{case_name}.fds"
    old_fds.replace(new_fds)
    text = new_fds.read_text(encoding="utf-8", errors="replace")
    text, head_count = re.subn(
        r"(&HEAD\b[^/]*CHID\s*=\s*')[^']+(')",
        rf"\g<1>{case_name}\g<2>", text, count=1, flags=re.I,
    )

    changes: dict[str, list[dict[str, float | str]]] = {key: [] for key in THICKNESS_M}

    def edit_surface(match: re.Match[str]) -> str:
        block = match.group(0)
        id_match = re.search(r"\bID\s*=\s*'([^']+)'", block, flags=re.I)
        thick_match = re.search(r"THICKNESS\(1\)\s*=\s*([-+0-9.Ee]+)", block, flags=re.I)
        if not id_match or not thick_match:
            return block
        surface_id = id_match.group(1)
        group = surface_group(surface_id)
        if group is None:
            return block
        old_value = float(thick_match.group(1))
        new_value = THICKNESS_M[group]
        changes[group].append({"surface_id": surface_id, "old_m": old_value, "new_m": new_value})
        return block[:thick_match.start(1)] + f"{new_value:.6g}" + block[thick_match.end(1):]

    text = re.sub(r"&SURF\b[\s\S]*?/", edit_surface, text, flags=re.I)
    missing = [group for group, records in changes.items() if not records]
    if head_count != 1 or missing:
        raise RuntimeError(f"Unexpected replacement result: HEAD={head_count}, missing={missing}")

    note = (
        "! Surface-layer thickness audit campaign; OBST geometry is unchanged.\n"
        f"! Q={q} J/cm2, W=100 kt, az=270, el=15; flux, combustion and criteria unchanged.\n"
        "! RADM=100 mm pending specimen verification; WINS=25 mm; BED cover=0.89 mm; "
        "CURT=3 mm; U4=6 mm.\n"
    )
    new_fds.write_text(note + text, encoding="utf-8")

    summary_path = output / "case_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.update(
        case=case_name,
        purpose="surface_layer_thickness_audit_campaign",
        adaptive_variant=True,
        source_case=source_name,
        source_case_root=source_root,
        changed_factor="surface_layer_thickness_only",
        thickness_m=THICKNESS_M,
        thickness_surface_blocks_changed={key: len(value) for key, value in changes.items()},
        thickness_change_records=changes,
        source_note=(
            "WINS/CURT/U4/RADM values restore Separated_merge_20260720.fds; "
            "BED 0.89 mm is the upper nylon-containing upholstery-fabric thickness "
            "reported in NBSIR 85-3280 Table 20 and remains provisional pending measured data"
        ),
        geometry_changed=False,
        external_flux_changed=False,
        combustion_changed=False,
        damage_thresholds_changed=False,
    )
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def main() -> None:
    for q in FLUENCES:
        print(build_one(q))


if __name__ == "__main__":
    main()

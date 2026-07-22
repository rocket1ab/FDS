#!/usr/bin/env python3
"""Build Q50-Q400 audited-thickness cases with source-backed upper HRRPUA values."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLUENCES = (50, 100, 200, 300, 400)
THICKNESS_M = {
    "RADM": 0.100,
    "WINS": 0.025,
    "BED": 0.00089,
    "CURT": 0.003,
    "U4": 0.006,
}
HRRPUA_KW_M2 = {
    "RADM": 840.0,
    "WINS": 806.0,
    "BED": 790.0,
    "CURT": 324.0,
    "U4": 840.0,
    "SEAT": 860.0,
    "H6": 259.0,
    "H7": 458.0,
}
SOURCES = {
    "RADM": "Uncoated glass-fibre reinforced epoxy cone peak 840 kW/m2 at 50 kW/m2 exposure; Materials 2015, 8, 5216",
    "WINS": "FSRI PMMA cone database maximum 25 kW/m2 replicate peak 805.8 kW/m2, rounded to 806",
    "BED": "Neat Nylon-6 upper-bound cone peak 790 kW/m2; bounding sensitivity pending mattress-cover qualification",
    "CURT": "NIST transportation-material privacy-curtain maximum peak 324 kW/m2",
    "U4": "Uncoated glass-fibre reinforced epoxy cone peak 840 kW/m2 at 50 kW/m2 exposure; Materials 2015, 8, 5216",
    "SEAT": "Raw aircraft-cabin polyurethane foam peak 859.9 kW/m2 at 35 kW/m2 exposure; Fire 2024, 7, 351",
    "H6": "PVC cone maximum peak 259 kW/m2 at 50 kW/m2 exposure; Asia-Oceania Symposium on Fire Science and Technology",
    "H7": "NIST transportation-material chloroprene diaphragm maximum peak 458 kW/m2",
}
SOURCE_URLS = {
    "RADM": "https://www.mdpi.com/1996-1944/8/8/5216",
    "WINS": "https://materials.fsri.org/materialdetail/polymethyl-methacrylate-pmma",
    "BED": "https://doi.org/10.1002/fam.2265",
    "CURT": "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=912697",
    "U4": "https://www.mdpi.com/1996-1944/8/8/5216",
    "SEAT": "https://www.mdpi.com/2571-6255/7/10/351",
    "H6": "https://publications.iafss.org/publications/aofst/3/189/view/aofst_3-189.pdf",
    "H7": "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=912697",
}


def classify_surface(block: str) -> str | None:
    id_match = re.search(r"\bID\s*=\s*'([^']+)'", block, flags=re.I)
    matl_match = re.search(r"MATL_ID\(1,1\)\s*=\s*'([^']+)'", block, flags=re.I)
    if not id_match or not matl_match:
        return None
    surface_id = id_match.group(1)
    material = matl_match.group(1)
    for group in ("RADM", "WINS", "BED", "CURT", "U4", "SEAT", "H6", "H7"):
        if surface_id.startswith(group + "_"):
            return group
    if "床垫" in surface_id:
        return "BED"
    if "窗帘" in surface_id:
        return "CURT"
    direct = {
        "EBLXW": "RADM",
        "BXSSL": "WINS",
        "HYBLXW": "U4",
        "JAZPM": "SEAT",
        "PVCSL": "H6",
        "CRXJ": "H7",
    }
    if material in direct:
        return direct[material]
    if material == "NLZW":
        thickness = re.search(r"THICKNESS\(1\)\s*=\s*([-+0-9.Ee]+)", block, flags=re.I)
        if thickness:
            return "BED" if float(thickness.group(1)) > 0.05 else "CURT"
    return None


def build_one(q: int) -> Path:
    source_name = f"Q{q:04d}_W0100_az270_el15_H1H7_v5_Qnorm"
    source = ROOT / "cases_qnorm" / source_name
    case_name = f"{source_name}_adapt_HRRupper_thickness_audit"
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
    thickness_changes = {key: 0 for key in THICKNESS_M}
    hrrpua_changes = {key: 0 for key in HRRPUA_KW_M2}

    def edit_surface(match: re.Match[str]) -> str:
        block = match.group(0)
        group = classify_surface(block)
        if group is None:
            return block
        if group in THICKNESS_M:
            block, count = re.subn(
                r"(THICKNESS\(1\)\s*=\s*)[-+0-9.Ee]+",
                rf"\g<1>{THICKNESS_M[group]:.6g}", block, count=1, flags=re.I,
            )
            thickness_changes[group] += count
        if group in HRRPUA_KW_M2:
            block, count = re.subn(
                r"(HRRPUA\s*=\s*)[-+0-9.Ee]+",
                rf"\g<1>{HRRPUA_KW_M2[group]:.1f}", block, count=1, flags=re.I,
            )
            hrrpua_changes[group] += count
        return block

    text = re.sub(r"&SURF\b[\s\S]*?/", edit_surface, text, flags=re.I)
    mpi = 20 if q == 50 else 32
    mesh_index = 0

    def remap_mesh_process(match: re.Match[str]) -> str:
        nonlocal mesh_index
        block = match.group(0)
        # FDS requires MPI_PROCESS values to be continuous and monotonically
        # increasing across MESH records, so assign contiguous mesh groups.
        process = mesh_index * mpi // 32
        mesh_index += 1
        return re.sub(
            r"(MPI_PROCESS\s*=\s*)\d+",
            rf"\g<1>{process}", block, count=1, flags=re.I,
        )

    # Q50 runs on the 20-core node. Map its 32 meshes onto ranks 0-19;
    # this changes only workload distribution, not the numerical/physical model.
    if mpi < 32:
        text = re.sub(r"&MESH\b[\s\S]*?/", remap_mesh_process, text, flags=re.I)
    missing_thickness = [key for key, count in thickness_changes.items() if count == 0]
    missing_hrrpua = [key for key, count in hrrpua_changes.items() if count == 0]
    if head_count != 1 or missing_thickness or missing_hrrpua:
        raise RuntimeError(
            f"Replacement failure: HEAD={head_count}, thickness={missing_thickness}, HRRPUA={missing_hrrpua}"
        )
    note = (
        "! Source-backed upper-bound HRRPUA sensitivity with audited surface thicknesses.\n"
        f"! Q={q} J/cm2, W=100 kt, az=270, el=15, T_END=1500 s.\n"
        "! Geometry, Q normalization, ignition temperatures, BURN_AWAY, probes and damage criteria unchanged.\n"
    )
    new_fds.write_text(note + text, encoding="utf-8")

    summary_path = output / "case_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.update(
        case=case_name,
        purpose="source_backed_upper_HRRPUA_with_audited_thickness",
        adaptive_variant=True,
        source_case=source_name,
        changed_factor="HRRPUA_and_previously_audited_surface_thickness",
        thickness_m=THICKNESS_M,
        hrrpua_kW_m2=HRRPUA_KW_M2,
        hrrpua_sources=SOURCES,
        hrrpua_source_urls=SOURCE_URLS,
        thickness_surface_blocks_changed=thickness_changes,
        hrrpua_surface_blocks_changed=hrrpua_changes,
        mpi=mpi,
        mesh_process_mapping="contiguous_balanced" if mpi < 32 else "source",
        geometry_changed=False,
        external_flux_changed=False,
        ignition_temperature_changed=False,
        burn_away_changed=False,
        damage_thresholds_changed=False,
        upper_bound_sensitivity_not_qualified_material_data=True,
    )
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def main() -> None:
    outputs = [build_one(q) for q in FLUENCES]
    manifest = {
        "campaign": "HRRupper_thickness_audit_20260722",
        "fluences_J_cm2": list(FLUENCES),
        "yield_kt": 100,
        "azimuth_deg": 270,
        "elevation_deg": 15,
        "t_end_s": 1500,
        "hrrpua_kW_m2": HRRPUA_KW_M2,
        "source_urls": SOURCE_URLS,
        "cases": [path.name for path in outputs],
    }
    (ROOT / "cases_adaptive" / "hrrpua_upper_campaign_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

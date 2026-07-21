#!/usr/bin/env python3
"""Build an arbitrary-fluence threshold case from the validated Q100 baseline."""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "cases_threshold"


def build(q: int) -> Path:
    if q <= 0:
        raise ValueError("Fluence must be positive")
    case_name = f"Q{q:04d}_W0100_az270_el15_H1H7_v5_Qnorm_threshold"
    case_dir = OUTPUT / case_name
    case_dir.mkdir(parents=True, exist_ok=True)

    exact_name = f"Q{q:04d}_W0100_az270_el15_H1H7_v5_Qnorm"
    exact_source = ROOT / "cases_qnorm" / exact_name
    source_name = exact_name if exact_source.exists() else "Q0100_W0100_az270_el15_H1H7_v5_Qnorm"
    source = ROOT / "cases_qnorm" / source_name
    source_q = q if exact_source.exists() else 100
    source_fds = source / f"{source_name}.fds"
    text = source_fds.read_text(encoding="utf-8", errors="replace")
    ratio = q / float(source_q)
    text = re.sub(
        r"EXTERNAL_FLUX\s*=\s*([0-9.Ee+-]+)(\s*,\s*RAMP_EF='NUCLEAR_RAMP')",
        lambda match: f"EXTERNAL_FLUX={int(round(float(match.group(1)) * ratio))}{match.group(2)}",
        text,
    )
    text, count = re.subn(
        r"(&HEAD\b[^/]*CHID\s*=\s*')[^']+(')",
        rf"\g<1>{case_name}\g<2>",
        text,
        count=1,
        flags=re.I,
    )
    if count != 1:
        raise RuntimeError("Could not replace CHID")
    text = re.sub(
        r"! v5_Qnorm exploratory case:[\s\S]*?! E0=[^\n]*\n",
        "",
        text,
        count=1,
    )

    source_summary = json.loads((source / "case_summary.json").read_text(encoding="utf-8"))
    integral = float(source_summary["nuclear_ramp_integral_s"])
    plane_e0 = q * 10.0 / integral
    note = (
        f"! Threshold search case: Q={q} J/cm2 at incident plane; W=100 kt; az=270; el=15.\n"
        "! Geometry, materials, probes, combustion parameters and damage criteria unchanged.\n"
        f"! E0={plane_e0:.6f} kW/m2; integral(NUCLEAR_RAMP)={integral:.9f} s.\n"
    )
    (case_dir / f"{case_name}.fds").write_text(note + text, encoding="utf-8")
    shutil.copy2(source / "monitor_registry.json", case_dir / "monitor_registry.json")

    rows = []
    with (source / "flux_faces.csv").open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        for row in reader:
            row["external_flux_kw_m2"] = str(int(round(float(row["external_flux_kw_m2"]) * ratio)))
            rows.append(row)
    with (case_dir / "flux_faces.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    max_flux = max(int(row["external_flux_kw_m2"]) for row in rows)
    summary = dict(source_summary)
    summary.update(
        case=case_name,
        purpose="automatic_fluence_threshold_search",
        Q_J_cm2=q,
        yield_kt=100,
        azimuth_deg=270,
        elevation_deg=15,
        plane_peak_irradiance_kw_m2=plane_e0,
        max_local_external_flux_kw_m2=max_flux,
        max_local_fluence_J_cm2=max_flux * integral * 0.1,
        threshold_search=True,
        source_case=source_name,
        materials_changed=False,
        damage_thresholds_changed=False,
    )
    (case_dir / "case_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return case_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("q", type=int)
    args = parser.parse_args()
    print(build(args.q))


if __name__ == "__main__":
    main()

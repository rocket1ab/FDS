#!/usr/bin/env python3
"""Build conservative numerical-stability variants without changing peak physics."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_CASES = ROOT / "cases"
STABLE_CASES = ROOT / "cases_stable"
FLUENCES = (50, 100, 200, 300, 400)


def patch_time(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        block = match.group(0).rstrip().rstrip("/")
        block = re.sub(r",?\s*DT\s*=\s*[-+\d.E]+", "", block, flags=re.I)
        block = re.sub(r",?\s*CFL_MAX\s*=\s*[-+\d.E]+", "", block, flags=re.I)
        return block + ", DT=0.002/"

    return re.sub(r"&TIME\b[\s\S]*?/", replace, text, count=1, flags=re.I)


def patch_combustion_ramp(text: str) -> tuple[str, int]:
    """Use an ignition-relative growth time instead of a global-time RAMP_Q."""
    changed = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal changed
        block = match.group(0)
        if "HRRPUA" not in block.upper():
            return block
        block, removed = re.subn(r",?\s*RAMP_Q\s*=\s*'[^']+'", "", block, flags=re.I)
        block = re.sub(r",?\s*TAU_Q\s*=\s*[-+\d.E]+", "", block, flags=re.I)
        if removed:
            changed += 1
        return block.rstrip().rstrip("/") + ", TAU_Q=10.0/"

    return re.sub(r"&SURF\b[\s\S]*?/", replace, text, flags=re.I), changed


def patch_solver(text: str) -> str:
    if not re.search(r"&CLIP\b", text, flags=re.I):
        text = re.sub(
            r"(&HEAD\b[\s\S]*?/)",
            r"\1\n&CLIP MINIMUM_DENSITY=0.01, MAXIMUM_DENSITY=10000.0/",
            text,
            count=1,
            flags=re.I,
        )
    if not re.search(r"&PRES\b", text, flags=re.I):
        text = re.sub(
            r"(&TIME\b[\s\S]*?/)",
            r"\1\n&PRES MAX_PRESSURE_ITERATIONS=100, VELOCITY_TOLERANCE=1.E-3/",
            text,
            count=1,
            flags=re.I,
        )
    if not re.search(r"&MISC\b", text, flags=re.I):
        text = re.sub(
            r"(&PRES\b[\s\S]*?/)", r"\1\n&MISC CHECK_HT=.TRUE., CFL_MAX=0.5/", text, count=1, flags=re.I
        )
    return text


def build_one(q: int) -> dict:
    source_name = f"Q{q:04d}_W0100_az270_el15_H1H7_v2"
    stable_name = f"Q{q:04d}_W0100_az270_el15_H1H7_v3_stable"
    source_dir = SOURCE_CASES / source_name
    stable_dir = STABLE_CASES / stable_name
    stable_dir.mkdir(parents=True, exist_ok=True)

    text = (source_dir / f"{source_name}.fds").read_text(encoding="utf-8", errors="replace")
    text = re.sub(
        r"(&HEAD\b[^/]*CHID\s*=\s*')[^']+(')", rf"\g<1>{stable_name}\g<2>", text, count=1, flags=re.I
    )
    text = patch_time(text)
    text, ramp_count = patch_combustion_ramp(text)
    text = patch_solver(text)
    note = (
        "! v3_stable: peak material HRRPUA and external flux are unchanged.\n"
        "! Numerical controls: TIME DT=0.002 s; MISC CFL_MAX=0.5; density clip; pressure iterations.\n"
        "! Delayed ignition uses TAU_Q=10 s; the former global RAMP_Q was already complete before ignition.\n"
    )
    text = note + text
    (stable_dir / f"{stable_name}.fds").write_text(text, encoding="utf-8")

    for filename in ("monitor_registry.json", "flux_faces.csv"):
        shutil.copy2(source_dir / filename, stable_dir / filename)
    summary = json.loads((source_dir / "case_summary.json").read_text(encoding="utf-8"))
    summary.update({
        "case": stable_name,
        "stability_version": "v3_stable",
        "dt_s": 0.002,
        "cfl_max": 0.5,
        "tau_q_s": 10.0,
        "pressure_iterations": 100,
        "peak_hrrpua_changed": False,
        "external_flux_changed": False,
        "patched_combustible_surfaces": ramp_count,
    })
    (stable_dir / "case_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    STABLE_CASES.mkdir(exist_ok=True)
    summaries = [build_one(q) for q in FLUENCES]
    manifest = {
        "version": "v3_stable",
        "source_version": "v2",
        "cases": summaries,
    }
    (STABLE_CASES / "stable_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

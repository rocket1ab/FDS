#!/usr/bin/env python3
"""Run a bounded, auditable Q400 optimization sequence on one FDS node."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases_adaptive"
BASE = "Q0400_W0100_az270_el15_H1H7_v5_Qnorm_adapt_combined_SEAT650_BED600_RF040_BAfalse_thin4mm_v1"
STATUS = ROOT / "queue" / "q400_combined_auto_optimization_status.json"

# Each new run adds exactly one bounded, source-supported change.
STEPS = [
    ("opt01_SEAT860", "SEAT", 860.0),
    ("opt02_BED790", "BED", 790.0),
    ("opt03_WINS500", "WINS", 500.0),
    ("opt04_U4600", "U4", 600.0),
]


def now() -> str:
    return datetime.now().astimezone().isoformat()


def write_status(state: dict) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now()
    temp = STATUS.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(STATUS)


def classify(surface_id: str) -> str | None:
    if surface_id.startswith("聚氨酯泡沫") or surface_id.startswith("SEAT_"):
        return "SEAT"
    if surface_id.startswith("尼龙织物_床垫") or surface_id.startswith("BED_"):
        return "BED"
    if surface_id.startswith("丙烯酸塑料") or surface_id.startswith("WINS_"):
        return "WINS"
    if surface_id.startswith("环氧玻璃纤维"):
        return "U4"
    return None


def set_group_hrrpua(text: str, group: str, value: float) -> tuple[str, int]:
    count = 0

    def edit(match: re.Match[str]) -> str:
        nonlocal count
        block = match.group(0)
        id_match = re.search(r"ID\s*=\s*'([^']+)'", block)
        if not id_match or classify(id_match.group(1)) != group:
            return block
        block, changed = re.subn(
            r"(HRRPUA\s*=\s*)[-+0-9.Ee]+",
            lambda item: item.group(1) + f"{value:.1f}",
            block,
            count=1,
            flags=re.I,
        )
        count += changed
        return block

    return re.sub(r"&SURF\b.*?/", edit, text, flags=re.S | re.I), count


def clone_variant(source_name: str, tag: str, group: str, value: float) -> str:
    new_name = f"{BASE}_{tag}"
    source_dir = CASES / source_name
    case_dir = CASES / new_name
    if case_dir.exists():
        return new_name
    case_dir.mkdir(parents=True)

    source_fds = source_dir / f"{source_name}.fds"
    text = source_fds.read_text(encoding="utf-8-sig").replace(source_name, new_name)
    text, changed = set_group_hrrpua(text, group, value)
    if changed == 0:
        raise RuntimeError(f"No {group} HRRPUA surfaces were changed")
    if re.search(r"BURN_AWAY\s*=\s*\.TRUE\.", text, flags=re.I):
        raise RuntimeError("BURN_AWAY changed from the required FALSE setting")

    note = (
        f"! Automatic bounded optimization step: {group} HRRPUA={value:g} kW/m2.\n"
        "! Q, yield, angle, geometry, other materials, probes and criteria unchanged.\n"
    )
    (case_dir / f"{new_name}.fds").write_text(note + text, encoding="utf-8")
    for filename in ("monitor_registry.json", "flux_faces.csv"):
        source = source_dir / filename
        if source.exists():
            shutil.copy2(source, case_dir / filename)

    summary = json.loads((source_dir / "case_summary.json").read_text(encoding="utf-8"))
    summary.update({
        "case": new_name,
        "source_case": source_name,
        "classification": "bounded cumulative optimization; not single-factor from original baseline",
        "changed_factor_this_step": f"{group}_HRRPUA",
        "changed_value_this_step_kW_m2": value,
        "created_at": now(),
    })
    values = summary.setdefault("optimization_hrrpua_kW_m2", {})
    values[group] = value
    (case_dir / "case_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (case_dir / ".preflight_ok").write_text(now(), encoding="utf-8")
    return new_name


def wait_for_completion(case_name: str, state: dict) -> None:
    case_dir = CASES / case_name
    exit_file = case_dir / ".fds_exit_code"
    while not exit_file.exists():
        state.update({"state": "running_or_waiting", "case": case_name})
        write_status(state)
        time.sleep(60)
    exit_code = int(exit_file.read_text().strip())
    log = (case_dir / "run.log").read_text(encoding="utf-8", errors="replace")
    if exit_code != 0 or "STOP: FDS completed successfully" not in log:
        raise RuntimeError(f"{case_name} abnormal exit={exit_code}")


def assess(case_name: str) -> dict:
    case_dir = CASES / case_name
    subprocess.run(
        ["python3", str(ROOT / "src" / "assess_results.py"), str(case_dir)],
        cwd=ROOT,
        check=True,
        stdout=(case_dir / "assessment_runner.log").open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )
    return json.loads((case_dir / "damage_assessment.json").read_text(encoding="utf-8"))


def run_fds(case_name: str, state: dict) -> None:
    case_dir = CASES / case_name
    state.update({"state": "running", "case": case_name, "started_at": now()})
    write_status(state)
    with (case_dir / "run.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(
            ["mpiexec", "-n", "32", "/home/zsh/FDS/FDS6/bin/fds", f"{case_name}.fds"],
            cwd=case_dir,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    (case_dir / ".fds_exit_code").write_text(str(result.returncode), encoding="utf-8")


def main() -> None:
    state = {
        "campaign": "Q400 combined bounded auto optimization",
        "fixed": {"Q_J_cm2": 400, "yield_kt": 100, "azimuth_deg": 270, "elevation_deg": 15},
        "steps": [{"tag": tag, "group": group, "value": value} for tag, group, value in STEPS],
        "history": [],
    }
    try:
        current = BASE
        wait_for_completion(current, state)
        result = assess(current)
        state["history"].append({
            "case": current,
            "severe_count": result["severe_count"],
            "sim_t_s": result["sim_t_s"],
        })
        write_status(state)
        if result.get("all_severe"):
            state["state"] = "success_17_of_17"
            write_status(state)
            return

        for tag, group, value in STEPS:
            next_case = clone_variant(current, tag, group, value)
            run_fds(next_case, state)
            wait_for_completion(next_case, state)
            result = assess(next_case)
            state["history"].append({
                "case": next_case,
                "severe_count": result["severe_count"],
                "sim_t_s": result["sim_t_s"],
                "changed_group": group,
                "changed_value_kW_m2": value,
            })
            write_status(state)
            if result.get("all_severe"):
                state["state"] = "success_17_of_17"
                write_status(state)
                return
            current = next_case

        state["state"] = "stopped_at_physical_bounds_without_17_of_17"
        write_status(state)
    except Exception as exc:
        state.update({"state": "stopped_on_error", "error": repr(exc)})
        write_status(state)
        raise


if __name__ == "__main__":
    main()

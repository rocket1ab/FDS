#!/usr/bin/env python3
"""Mirror detached FDS log progress into the GUI queue status file."""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STEP_RE = re.compile(r"Time Step:\s+(\d+),\s+Simulation Time:\s+([\d.]+)\s+s")


def stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_atomic(path: Path, data: dict) -> None:
    temp = path.with_suffix(".live.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", required=True)
    parser.add_argument("--interval", type=float, default=15.0)
    args = parser.parse_args()
    status_path = ROOT / "queue" / f"{args.node}_status.json"

    while True:
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if status.get("state") in {"queue_complete", "queue_failed"}:
                return
            case = status.get("case")
            if case and (case.endswith(("_v3_stable", "_v4_legacy_stable", "_v5_Qnorm", "_v6_probe_fixed")) or "_adapt_" in case):
                if "_adapt_" in case:
                    case_dir = "cases_adaptive"
                elif case.endswith("_v6_probe_fixed"):
                    case_dir = "cases_probe_corrected"
                elif case.endswith("_v5_Qnorm"):
                    case_dir = "cases_qnorm"
                else:
                    case_dir = "cases_legacy_stable" if case.endswith("_v4_legacy_stable") else "cases_stable"
                log_path = ROOT / case_dir / case / "run.log"
                if log_path.exists():
                    tail = log_path.read_bytes()[-65536:].decode("utf-8", errors="replace")
                    steps = STEP_RE.findall(tail)
                    if steps:
                        step, sim_time = steps[-1]
                        status.update(
                            time_step=int(step),
                            simulation_time_s=float(sim_time),
                            fds_processes=32,
                            busy_reason="running_corrected_qnorm_case",
                            progress_source="run.log",
                            updated_at=stamp(),
                        )
                        write_atomic(status_path, status)
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

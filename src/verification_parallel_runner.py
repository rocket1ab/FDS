#!/usr/bin/env python3
"""Run the verification campaign in a second, isolated slot on node03."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import queue_runner as runner


ROOT = Path(__file__).resolve().parents[1]
NODE = "node03"
SLOT = "node03_verification"


def wait_for_capacity(required_cores: int) -> None:
    """Wait for a second slot while allowing the existing 32-rank angle run."""
    clear = 0
    while clear < 2:
        command = (
            "printf '%s %s %s\\n' \"$(pgrep -c -x fds || true)\" "
            "\"$(nproc --all)\" \"$(cut -d' ' -f1 /proc/loadavg)\""
        )
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=8", NODE, command],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 255:
            clear = 0
            runner.write_status(NODE, state="node_unreachable", error="SSH connection failed")
        else:
            fds_count, logical_cpus, load_1m = result.stdout.strip().split()[-3:]
            fds_count = int(fds_count)
            logical_cpus = int(logical_cpus)
            load_1m = float(load_1m)
            capacity_ok = fds_count + required_cores <= logical_cpus
            load_ok = load_1m + required_cores <= logical_cpus * 0.80
            clear = clear + 1 if capacity_ok and load_ok else 0
            runner.write_status(
                NODE,
                state="confirming_capacity" if clear else "waiting_for_capacity",
                clear_checks=clear,
                fds_processes=fds_count,
                logical_cpus=logical_cpus,
                load_1m=round(load_1m, 2),
                required_cores=required_cores,
                available_process_slots=logical_cpus - fds_count,
                capacity_ok=capacity_ok,
                load_ok=load_ok,
            )
        if clear < 2:
            time.sleep(30)


def main() -> None:
    manifest = json.loads(
        (ROOT / "cases_verification" / "verification_manifest.json").read_text(encoding="utf-8")
    )
    # Yield cases retain the validated grid/probes and can use the spare slot
    # immediately. Coarse-grid cases follow after their rebuilt probes pass
    # preflight; keeping them in this runner preserves one ordered slot.
    cases = manifest["yield_cases_in_order"] + manifest["grid_cases_in_order"]
    lock = ROOT / "queue" / f"{SLOT}.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        raise SystemExit(f"Verification slot already exists: {lock}")

    original_write_status = runner.write_status

    def slot_status(_node: str, **fields) -> None:
        original_write_status(SLOT, physical_node=NODE, **fields)

    runner.write_status = slot_status
    failed = False
    try:
        slot_status(NODE, state="queued", cases=cases)
        wait_for_capacity(runner.case_mpi(cases[0]))
        if not runner.run_preflight(NODE, cases[0]):
            failed = True
        for case in cases:
            if failed:
                break
            wait_for_capacity(runner.case_mpi(case))
            if not runner.run_case(NODE, case):
                failed = True
                break
        slot_status(NODE, state="queue_failed" if failed else "queue_complete")
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run an isolated queue slot when a physical node has spare FDS capacity."""
from __future__ import annotations

import argparse
import os
import subprocess
import time
from pathlib import Path

import queue_runner as runner

ROOT = Path(__file__).resolve().parents[1]


def wait_for_capacity(node: str, required: int) -> None:
    clear = 0
    while clear < 2:
        command = (
            "printf '%s %s %s\\n' \"$(pgrep -c -x fds || true)\" "
            "\"$(nproc --all)\" \"$(cut -d' ' -f1 /proc/loadavg)\""
        )
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=8", node, command],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            clear = 0
            runner.write_status(node, state="node_unreachable", error="SSH capacity check failed")
        else:
            count, cpus, load = result.stdout.strip().split()[-3:]
            count, cpus, load = int(count), int(cpus), float(load)
            capacity_ok = count + required <= cpus
            # The one-minute load average lags recently completed preflights.
            # Keep FDS ranks within CPU count and allow only a small load-average
            # margin so genuinely free ranks can be used without oversubscribing.
            load_ok = load + required <= cpus * 1.05
            clear = clear + 1 if capacity_ok and load_ok else 0
            runner.write_status(
                node,
                state="confirming_capacity" if clear else "waiting_for_capacity",
                clear_checks=clear, fds_processes=count, logical_cpus=cpus,
                load_1m=round(load, 2), required_cores=required,
                available_process_slots=cpus - count,
                capacity_ok=capacity_ok, load_ok=load_ok,
            )
        if clear < 2:
            time.sleep(30)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", required=True)
    parser.add_argument("--slot", required=True)
    parser.add_argument("cases", nargs="+")
    args = parser.parse_args()
    lock = ROOT / "queue" / f"{args.slot}.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        raise SystemExit(f"Slot already exists: {lock}")

    original_write = runner.write_status

    def slot_status(_node: str, **fields) -> None:
        original_write(args.slot, physical_node=args.node, **fields)

    runner.write_status = slot_status
    failed = False
    try:
        slot_status(args.node, state="queued", cases=args.cases)
        wait_for_capacity(args.node, runner.case_mpi(args.cases[0]))
        if not runner.run_preflight(args.node, args.cases[0]):
            failed = True
        for case in args.cases:
            if failed:
                break
            wait_for_capacity(args.node, runner.case_mpi(case))
            if not runner.run_case(args.node, case):
                failed = True
        slot_status(args.node, state="queue_failed" if failed else "queue_complete")
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

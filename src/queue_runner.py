#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def stamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_status(node: str, **fields):
    path = ROOT / "queue" / f"{node}_status.json"
    current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    current.update(fields, node=node, updated_at=stamp())
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def node_busy(node: str):
    result = subprocess.run(["ssh", "-o", "ConnectTimeout=8", node, "pgrep -x fds >/dev/null"], timeout=15)
    if result.returncode == 255:
        raise ConnectionError(f"SSH connection to {node} failed")
    return result.returncode == 0


def wait_for_idle(node: str):
    clear = 0
    while clear < 2:
        try:
            busy = node_busy(node)
            clear = 0 if busy else clear + 1
            write_status(node, state="waiting_for_idle" if busy else "confirming_idle", clear_checks=clear)
        except Exception as exc:
            clear = 0
            write_status(node, state="node_unreachable", error=str(exc))
        if clear < 2:
            time.sleep(30)


def run_preflight(node: str, case_name: str):
    """Run the first case to 0.01 s so formal work starts only after FDS accepts it."""
    source = ROOT / "cases" / case_name / f"{case_name}.fds"
    work = ROOT / "queue" / f"preflight_{node}"
    work.mkdir(parents=True, exist_ok=True)
    for path in work.iterdir():
        if path.is_file():
            path.unlink()

    chid = f"preflight_{node}_H1H7_v2"
    text = source.read_text(encoding="utf-8", errors="replace")
    text, head_count = re.subn(r"&HEAD\s+CHID='[^']*'\s*/", f"&HEAD CHID='{chid}'/", text, count=1)
    text, time_count = re.subn(r"&TIME\s+T_END\s*=\s*[^/]+/", "&TIME T_END=0.01/", text, count=1)
    if head_count != 1 or time_count != 1:
        raise ValueError("Could not create preflight input from HEAD/TIME records")
    fds = work / f"{chid}.fds"
    fds.write_text(text, encoding="utf-8")

    command = (
        f"cd '{work}' && timeout 900 mpiexec -n 32 "
        f"/home/zsh/FDS/FDS6/bin/fds '{fds.name}' > preflight.log 2>&1"
    )
    write_status(node, state="preflight", case=case_name, preflight_chid=chid)
    result = subprocess.run(["ssh", "-o", "ServerAliveInterval=30", node, command])
    log = (work / "preflight.log").read_text(encoding="utf-8", errors="replace") if (work / "preflight.log").exists() else ""
    accepted = result.returncode == 0 and "ERROR:" not in log and "completed successfully" in log.lower()
    write_status(node, state="preflight_passed" if accepted else "preflight_failed",
                 case=case_name, preflight_exit_code=result.returncode,
                 preflight_error_detected="ERROR:" in log)
    return accepted


def run_case(node: str, case_name: str):
    case_dir = ROOT / "cases" / case_name
    fds = case_dir / f"{case_name}.fds"
    command = f"cd '{case_dir}' && mpiexec -n 32 /home/zsh/FDS/FDS6/bin/fds '{fds.name}' > run.log 2>&1"
    write_status(node, state="running", case=case_name, started_at=stamp())
    result = subprocess.run(["ssh", "-o", "ServerAliveInterval=30", node, command])
    write_status(node, state="assessing", case=case_name, fds_exit_code=result.returncode)
    assessment = subprocess.run(["python3", str(ROOT / "src" / "assess_results.py"), str(case_dir)],
                                capture_output=True, text=True)
    (case_dir / "assessment.log").write_text(assessment.stdout + assessment.stderr, encoding="utf-8")
    write_status(node, state="case_complete" if result.returncode == 0 and assessment.returncode == 0 else "case_failed",
                 case=case_name, fds_exit_code=result.returncode, assessment_exit_code=assessment.returncode,
                 completed_at=stamp())
    return result.returncode == 0 and assessment.returncode == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", required=True)
    parser.add_argument("cases", nargs="+")
    args = parser.parse_args()
    lock = ROOT / "queue" / f"{args.node}.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        raise SystemExit(f"Queue already exists for {args.node}")
    try:
        write_status(args.node, state="queued", cases=args.cases)
        failed = False
        wait_for_idle(args.node)
        if not run_preflight(args.node, args.cases[0]):
            failed = True
        for case in args.cases:
            if failed:
                break
            wait_for_idle(args.node)
            if not run_case(args.node, case):
                failed = True
                break
        write_status(args.node, state="queue_failed" if failed else "queue_complete")
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

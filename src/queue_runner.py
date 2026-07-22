#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SSH_OPTIONS = ["-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3"]


def case_root(case_name: str) -> Path:
    if "_threshold" in case_name:
        return ROOT / "cases_threshold"
    if "_adapt_" in case_name:
        return ROOT / "cases_adaptive"
    if case_name.endswith("_v6_probe_fixed"):
        return ROOT / "cases_probe_corrected"
    if case_name.endswith("_v5_Qnorm"):
        return ROOT / "cases_qnorm"
    if case_name.endswith("_v4_legacy_stable"):
        return ROOT / "cases_legacy_stable"
    if case_name.endswith("_v3_stable"):
        return ROOT / "cases_stable"
    return ROOT / "cases"


def case_mpi(case_name: str) -> int:
    summary = case_root(case_name) / case_name / "case_summary.json"
    if summary.exists():
        return int(json.loads(summary.read_text(encoding="utf-8")).get("mpi", 32))
    return 32


def stamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_status(node: str, **fields):
    path = ROOT / "queue" / f"{node}_status.json"
    current = {} if fields.get("state") == "queued" else (
        json.loads(path.read_text(encoding="utf-8")) if path.exists() else {})
    if fields.get("state") != "node_unreachable":
        current.pop("error", None)
    current.update(fields, node=node, updated_at=stamp())
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def node_busy(node: str, required_cores: int = 32):
    command = "printf '%s %s %s\\n' \"$(pgrep -c -x fds || true)\" \"$(nproc --all)\" \"$(cut -d' ' -f1 /proc/loadavg)\""
    result = subprocess.run(["ssh", "-o", "ConnectTimeout=8", node, command],
                            capture_output=True, text=True, timeout=15)
    if result.returncode == 255:
        raise ConnectionError(f"SSH connection to {node} failed")
    fds_count, logical_cpus, load_1m = result.stdout.strip().split()[-3:]
    telemetry = {"fds_processes": int(fds_count), "logical_cpus": int(logical_cpus),
                 "load_1m": round(float(load_1m), 2)}
    # Allow a small residual system load when a case uses all logical CPUs. Without
    # this floor, a 20-rank case on a 20-core node can never pass the idle check.
    load_limit = max(telemetry["logical_cpus"] - required_cores,
                     telemetry["logical_cpus"] * 0.20)
    telemetry.update(required_cores=required_cores, load_limit=round(load_limit, 2))
    telemetry["busy_reason"] = "fds" if telemetry["fds_processes"] else (
        "insufficient_free_cpu" if telemetry["load_1m"] > load_limit else "idle")
    return telemetry["busy_reason"] != "idle", telemetry


def wait_for_idle(node: str, required_cores: int = 32):
    clear = 0
    while clear < 2:
        try:
            busy, telemetry = node_busy(node, required_cores)
            clear = 0 if busy else clear + 1
            write_status(node, state="waiting_for_idle" if busy else "confirming_idle",
                         clear_checks=clear, **telemetry)
        except Exception as exc:
            clear = 0
            write_status(node, state="node_unreachable", error=str(exc))
        if clear < 2:
            time.sleep(30)


def run_preflight(node: str, case_name: str):
    """Run the first case to 0.01 s so formal work starts only after FDS accepts it."""
    source = case_root(case_name) / case_name / f"{case_name}.fds"
    work = ROOT / "queue" / f"preflight_{node}"
    work.mkdir(parents=True, exist_ok=True)
    for path in work.iterdir():
        if path.is_file():
            path.unlink()

    chid = f"preflight_{node}_H1H7_v2"
    text = source.read_text(encoding="utf-8", errors="replace")
    text, head_count = re.subn(r"&HEAD\s+CHID='[^']*'\s*/", f"&HEAD CHID='{chid}'/", text, count=1)
    text, time_count = re.subn(r"(T_END\s*=\s*)[-+\d.E]+", r"\g<1>0.01", text, count=1, flags=re.I)
    if head_count != 1 or time_count != 1:
        raise ValueError("Could not create preflight input from HEAD/TIME records")
    fds = work / f"{chid}.fds"
    fds.write_text(text, encoding="utf-8")

    mpi = case_mpi(case_name)
    command = (
        f"cd '{work}' && timeout 900 mpiexec -n {mpi} "
        f"/home/zsh/FDS/FDS6/bin/fds '{fds.name}' > preflight.log 2>&1"
    )
    write_status(node, state="preflight", case=case_name, preflight_chid=chid)
    result = subprocess.run(["ssh", *SSH_OPTIONS, node, command])
    log = (work / "preflight.log").read_text(encoding="utf-8", errors="replace") if (work / "preflight.log").exists() else ""
    accepted = result.returncode == 0 and "ERROR:" not in log and "completed successfully" in log.lower()
    write_status(node, state="preflight_passed" if accepted else "preflight_failed",
                 case=case_name, preflight_exit_code=result.returncode,
                 preflight_error_detected="ERROR:" in log)
    return accepted


def run_case(node: str, case_name: str):
    case_dir = case_root(case_name) / case_name
    fds = case_dir / f"{case_name}.fds"
    marker = ".fds_exit_code"
    mpi = case_mpi(case_name)
    inner = (
        f"mpiexec -n {mpi} /home/zsh/FDS/FDS6/bin/fds {shlex.quote(fds.name)} > run.log 2>&1; "
        f"printf '%s' $? > {marker}"
    )
    command = (
        f"cd {shlex.quote(str(case_dir))} && rm -f {marker} && "
        f"setsid -f bash -c {shlex.quote(inner)} > launcher.log 2>&1 < /dev/null"
    )
    write_status(node, state="running", case=case_name, started_at=stamp())
    launched = subprocess.run(["ssh", *SSH_OPTIONS, node, command], timeout=30)
    if launched.returncode != 0:
        write_status(node, state="case_failed", case=case_name,
                     failure_reason="remote_launch_failed", fds_exit_code=launched.returncode)
        return False

    lost_checks = 0
    result_code = None
    while result_code is None:
        poll = (
            f"cd {shlex.quote(str(case_dir))} && "
            f"if [ -f {marker} ]; then printf 'DONE '; cat {marker}; "
            f"elif pgrep -af {shlex.quote('fds.*' + case_name)} >/dev/null || "
            f"pgrep -af {shlex.quote('mpiexec.*' + case_name)} >/dev/null; then echo RUNNING; "
            "else echo LOST; fi; "
            "grep -a 'Time Step:' run.log 2>/dev/null | tail -1"
        )
        try:
            status = subprocess.run(["ssh", *SSH_OPTIONS, node, poll], capture_output=True,
                                    text=True, timeout=30)
            output = status.stdout.strip()
            done = re.search(r"DONE\s+(-?\d+)", output)
            step = re.search(r"Time Step:\s+(\d+),\s+Simulation Time:\s+([\d.]+)\s+s", output)
            if done:
                result_code = int(done.group(1))
            elif "RUNNING" in output:
                lost_checks = 0
                fields = {"state": "running", "case": case_name}
                if step:
                    fields.update(time_step=int(step.group(1)), simulation_time_s=float(step.group(2)))
                write_status(node, **fields)
            else:
                lost_checks += 1
                if lost_checks >= 3:
                    write_status(node, state="case_failed", case=case_name,
                                 failure_reason="remote_process_lost")
                    return False
        except Exception as exc:
            write_status(node, state="running_unreachable", case=case_name, error=str(exc))
        if result_code is None:
            time.sleep(30)

    log_path = case_dir / "run.log"
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    completed = "STOP: FDS completed successfully" in log and "Numerical Instability" not in log
    if result_code != 0 or not completed:
        write_status(node, state="case_failed", case=case_name,
                     fds_exit_code=result_code, normal_fds_completion=False,
                     failure_reason="numerical_instability" if "Numerical Instability" in log else "incomplete_fds_run",
                     completed_at=stamp())
        return False
    write_status(node, state="assessing", case=case_name, fds_exit_code=result_code,
                 normal_fds_completion=True)
    assessment = subprocess.run(["python3", str(ROOT / "src" / "assess_results.py"), str(case_dir)],
                                capture_output=True, text=True)
    (case_dir / "assessment.log").write_text(assessment.stdout + assessment.stderr, encoding="utf-8")
    write_status(node, state="case_complete" if assessment.returncode == 0 else "case_failed",
                 case=case_name, fds_exit_code=result_code, assessment_exit_code=assessment.returncode,
                 completed_at=stamp())
    return assessment.returncode == 0


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
        wait_for_idle(args.node, case_mpi(args.cases[0]))
        if not run_preflight(args.node, args.cases[0]):
            failed = True
        for case in args.cases:
            if failed:
                break
            wait_for_idle(args.node, case_mpi(case))
            if not run_case(args.node, case):
                failed = True
                break
        write_status(args.node, state="queue_failed" if failed else "queue_complete")
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

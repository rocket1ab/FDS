#!/usr/bin/env python3
"""Deploy the STL-filled U06 case in a dedicated node04 capacity slot."""
from __future__ import annotations

import argparse
import json
import posixpath
import shlex
from pathlib import Path

import paramiko


ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path(r"D:\Pyrosim\radiation_ignition_damage_workflow_20260716\gui_windows\user_config.json")
REMOTE = "/home/zsh/FDS/FDS6/radiation_ignition_damage_workflow_20260720_H1_H7"
CASE = "Q0400_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRtable_seatSTLfill_v1"
NODE = "node04"
SLOT = "node04_seat_stl_fill"


def mkdirs(sftp: paramiko.SFTPClient, path: str) -> None:
    current = ""
    for part in path.strip("/").split("/"):
        current += "/" + part
        try:
            sftp.stat(current)
        except OSError:
            sftp.mkdir(current)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default=CASE)
    parser.add_argument("--node", default=NODE)
    parser.add_argument("--slot", default=SLOT)
    args = parser.parse_args()
    case_name = args.case
    node = args.node
    slot = args.slot
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        cfg["host"], port=int(cfg.get("port", 22)), username=cfg["user"],
        password=cfg.get("password") or None, key_filename=cfg.get("key_path") or None,
        timeout=15, banner_timeout=15, auth_timeout=15,
    )
    try:
        sftp = client.open_sftp()
        local_case = ROOT / "cases_adaptive" / case_name
        remote_case = posixpath.join(REMOTE, "cases_adaptive", case_name)
        mkdirs(sftp, remote_case)
        for filename in (f"{case_name}.fds", "case_summary.json", "monitor_registry.json", "flux_faces.csv"):
            sftp.put(str(local_case / filename), posixpath.join(remote_case, filename))
        for filename in ("parallel_capacity_runner.py", "queue_runner.py", "assess_results.py"):
            sftp.put(str(ROOT / "src" / filename), posixpath.join(REMOTE, "src", filename))
        sftp.close()

        command = (
            f"cd {shlex.quote(REMOTE)} && mkdir -p queue && "
            f"if [ -e queue/{slot}.lock ]; then echo SLOT_EXISTS; "
            f"else nohup /usr/bin/python3.11 src/parallel_capacity_runner.py "
            f"--node {node} --slot {slot} {shlex.quote(case_name)} "
            f"> queue/{slot}.log 2>&1 < /dev/null & echo SLOT_STARTED:$!; fi"
        )
        _, stdout, stderr = client.exec_command(command, timeout=30)
        print(stdout.read().decode("utf-8", errors="replace").strip())
        error = stderr.read().decode("utf-8", errors="replace").strip()
        if error:
            raise RuntimeError(error)
    finally:
        client.close()


if __name__ == "__main__":
    main()

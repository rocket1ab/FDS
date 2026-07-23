#!/usr/bin/env python3
"""Deploy the STL-filled U06 case in a dedicated node04 capacity slot."""
from __future__ import annotations

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
        local_case = ROOT / "cases_adaptive" / CASE
        remote_case = posixpath.join(REMOTE, "cases_adaptive", CASE)
        mkdirs(sftp, remote_case)
        for filename in (f"{CASE}.fds", "case_summary.json", "monitor_registry.json", "flux_faces.csv"):
            sftp.put(str(local_case / filename), posixpath.join(remote_case, filename))
        for filename in ("parallel_capacity_runner.py", "queue_runner.py", "assess_results.py"):
            sftp.put(str(ROOT / "src" / filename), posixpath.join(REMOTE, "src", filename))
        sftp.close()

        command = (
            f"cd {shlex.quote(REMOTE)} && mkdir -p queue && "
            f"if [ -e queue/{SLOT}.lock ]; then echo SLOT_EXISTS; "
            f"else nohup /usr/bin/python3.11 src/parallel_capacity_runner.py "
            f"--node {NODE} --slot {SLOT} {shlex.quote(CASE)} "
            f"> queue/{SLOT}.log 2>&1 < /dev/null & echo SLOT_STARTED:$!; fi"
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

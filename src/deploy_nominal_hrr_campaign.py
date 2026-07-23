#!/usr/bin/env python3
"""Deploy and launch the nominal-HRRPUA fluence campaign in spare-node slots."""
from __future__ import annotations

import json
import posixpath
import shlex
from pathlib import Path

import paramiko


ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path(r"D:\Pyrosim\radiation_ignition_damage_workflow_20260716\gui_windows\user_config.json")
REMOTE = "/home/zsh/FDS/FDS6/radiation_ignition_damage_workflow_20260720_H1_H7"
SLOTS = {
    "node03_nominal_hrr": ("node03", [200]),
    "node04_nominal_hrr": ("node04", [50, 300]),
    "node05_nominal_hrr": ("node05", [100, 400]),
}


def case_name(q: int) -> str:
    return f"Q{q:04d}_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRnominal_thickness_audit_v1"


def mkdirs(sftp: paramiko.SFTPClient, remote: str) -> None:
    current = ""
    for part in remote.strip("/").split("/"):
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
        for slot, (_, q_values) in SLOTS.items():
            for q in q_values:
                name = case_name(q)
                local = ROOT / "cases_adaptive" / name
                remote = posixpath.join(REMOTE, "cases_adaptive", name)
                mkdirs(sftp, remote)
                for filename in (f"{name}.fds", "case_summary.json", "monitor_registry.json", "flux_faces.csv"):
                    sftp.put(str(local / filename), posixpath.join(remote, filename))
        for filename in ("parallel_capacity_runner.py", "queue_runner.py", "assess_results.py"):
            sftp.put(str(ROOT / "src" / filename), posixpath.join(REMOTE, "src", filename))
        sftp.put(
            str(ROOT / "cases_adaptive" / "nominal_hrr_campaign_manifest.json"),
            posixpath.join(REMOTE, "cases_adaptive", "nominal_hrr_campaign_manifest.json"),
        )
        sftp.close()

        for slot, (node, q_values) in SLOTS.items():
            cases = " ".join(shlex.quote(case_name(q)) for q in q_values)
            command = (
                f"cd {shlex.quote(REMOTE)} && mkdir -p queue && "
                f"if [ -e queue/{shlex.quote(slot)}.lock ]; then echo {slot}:EXISTS; "
                f"else nohup /usr/bin/python3.11 src/parallel_capacity_runner.py "
                f"--node {shlex.quote(node)} --slot {shlex.quote(slot)} {cases} "
                f"> queue/{shlex.quote(slot)}.log 2>&1 < /dev/null & echo {slot}:STARTED:$!; fi"
            )
            _, stdout, stderr = client.exec_command(command, timeout=30)
            print(stdout.read().decode("utf-8", errors="replace").strip())
            error = stderr.read().decode("utf-8", errors="replace").strip()
            if error:
                print(f"{slot}:STDERR:{error}")
    finally:
        client.close()


if __name__ == "__main__":
    main()

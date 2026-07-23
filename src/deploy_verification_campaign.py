#!/usr/bin/env python3
"""Deploy selected verification inputs and start their ordered remote queue."""
from __future__ import annotations

import json
import posixpath
import shlex
import stat
from pathlib import Path

import paramiko


ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path(r"D:\Pyrosim\radiation_ignition_damage_workflow_20260716\gui_windows\user_config.json")
REMOTE = "/home/zsh/FDS/FDS6/radiation_ignition_damage_workflow_20260720_H1_H7"


def mkdirs(sftp: paramiko.SFTPClient, remote: str) -> None:
    current = ""
    for part in remote.strip("/").split("/"):
        current += "/" + part
        try:
            sftp.stat(current)
        except OSError:
            sftp.mkdir(current)


def upload_tree(sftp: paramiko.SFTPClient, local: Path, remote: str) -> None:
    mkdirs(sftp, remote)
    for path in local.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(local).as_posix()
        destination = posixpath.join(remote, relative)
        mkdirs(sftp, posixpath.dirname(destination))
        sftp.put(str(path), destination)


def main() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "cases_verification" / "verification_manifest.json").read_text(encoding="utf-8"))
    cases = manifest["grid_cases_in_order"] + manifest["yield_cases_in_order"]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(cfg["host"], port=int(cfg.get("port", 22)), username=cfg["user"],
                   password=cfg.get("password") or None, key_filename=cfg.get("key_path") or None,
                   timeout=15, banner_timeout=15, auth_timeout=15)
    try:
        sftp = client.open_sftp()
        upload_tree(sftp, ROOT / "cases_verification", REMOTE + "/cases_verification")
        for name in ("queue_runner.py", "assess_results.py", "update_independence_report.py",
                     "verification_parallel_runner.py"):
            sftp.put(str(ROOT / "src" / name), REMOTE + "/src/" + name)
        sftp.put(str(ROOT / "reports" / "grid_and_yield_independence_verification.md"),
                 REMOTE + "/reports/grid_and_yield_independence_verification.md")
        sftp.close()
        inner = (
            f"cd {shlex.quote(REMOTE)} && "
            "if [ -e queue/node02.lock ]; then p=$(cat queue/node02.lock 2>/dev/null); "
            "case \"$(ps -p \"$p\" -o args= 2>/dev/null)\" in *'queue_runner.py --node node02'*) kill \"$p\" 2>/dev/null || true;; esac; "
            "rm -f queue/node02.lock; fi; "
            "if [ -e queue/verification_node03_waiter.pid ]; then p=$(cat queue/verification_node03_waiter.pid); "
            "case \"$(ps -p \"$p\" -o args= 2>/dev/null)\" in *'Q0050_W0100_grid_coarse'*) kill \"$p\" 2>/dev/null || true;; esac; "
            "rm -f queue/verification_node03_waiter.pid; fi; "
            "if [ -e queue/node03_verification.lock ] && "
            "grep -q '\"state\": \"waiting_for_idle\"' queue/node03_verification_status.json 2>/dev/null; then "
            "p=$(cat queue/node03_verification.lock); "
            "case \"$(ps -p \"$p\" -o args= 2>/dev/null)\" in *verification_parallel_runner.py*) "
            "kill \"$p\" 2>/dev/null || true; sleep 1; rm -f queue/node03_verification.lock;; esac; fi; "
            "if [ -e queue/node03_verification.lock ]; then echo VERIFICATION_SLOT_EXISTS; "
            "else nohup /usr/bin/python3.11 src/verification_parallel_runner.py "
            "> queue/verification_node03.log 2>&1 < /dev/null & echo VERIFICATION_STARTED:$!; fi"
        )
        _, stdout, stderr = client.exec_command(inner, timeout=30)
        print(stdout.read().decode("utf-8", errors="replace"))
        error = stderr.read().decode("utf-8", errors="replace").strip()
        if error:
            print(error)
    finally:
        client.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Read only the node03 verification slot and process state."""
import json
from pathlib import Path

import paramiko

CONFIG = Path(r"D:\Pyrosim\radiation_ignition_damage_workflow_20260716\gui_windows\user_config.json")
BASE = "/home/zsh/FDS/FDS6/radiation_ignition_damage_workflow_20260720_H1_H7"

cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(cfg["host"], port=int(cfg.get("port", 22)), username=cfg["user"],
               password=cfg.get("password") or None, key_filename=cfg.get("key_path") or None,
               timeout=15, banner_timeout=15, auth_timeout=15)
command = (
    "ssh -o ConnectTimeout=8 node03 \"echo CPU=\\$(nproc) LOAD=\\$(cut -d' ' -f1 /proc/loadavg); "
    "pgrep -a -x fds | sed -n '1p;$p'; echo FDS=\\$(pgrep -c -x fds)\"; "
    f"echo STATUS; cat '{BASE}/queue/node03_verification_status.json'; "
    f"echo LOG; tail -30 '{BASE}/queue/verification_node03.log'"
)
_, stdout, stderr = client.exec_command(command, timeout=30)
print(stdout.read().decode("utf-8", errors="replace"))
error = stderr.read().decode("utf-8", errors="replace")
if error:
    print(error)
client.close()

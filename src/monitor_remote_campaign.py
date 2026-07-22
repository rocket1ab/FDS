#!/usr/bin/env python3
"""Read-only status probe for the active H1-H7 remote campaign."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import paramiko


CONFIG = Path(r"D:\Pyrosim\radiation_ignition_damage_workflow_20260716\gui_windows\user_config.json")
BASE = "/home/zsh/FDS/FDS6/radiation_ignition_damage_workflow_20260720_H1_H7"
NODES = ("node01", "node03", "node04", "node05")
ACTIVE_CASES = (
    "cases_adaptive/Q0050_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRupper_thickness_audit",
    "cases_adaptive/Q0200_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRupper_thickness_audit",
    "cases_adaptive/Q0400_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRupper_thickness_audit",
    "cases_adaptive/Q0200_W0100_az060_el75_H1H7_v5_Qnorm_adapt_HRRupper_thickness_audit_angle",
)


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
        commands = ["date '+CHECK_TIME=%F %T %z'"]
        for node in NODES:
            inner = (
                "echo HOST=$(hostname); "
                "echo FDS_COUNT=$(ps -u zsh -o args= | grep -E '(^|/)(fds|fds_)[[:space:]]' | grep -v grep | wc -l); "
                "ps -u zsh -o pid=,etimes=,args= | grep -E '(^|/)(fds|fds_)[[:space:]]' | grep -v grep | head -40"
            )
            commands.append(f"echo '=== {node} ==='; ssh -o ConnectTimeout=7 {node} {shlex.quote(inner)} 2>&1")
        commands.append(
            f"echo '=== QUEUES ==='; find {shlex.quote(BASE)} -maxdepth 3 -type f "
            "\\( -name 'queue_status*.json' -o -name 'queue_state*.json' -o -name '*status*.json' "
            "-o -name '*.running' -o -name '*.done' -o -name '*.failed' \\) "
            "-printf '%TY-%Tm-%Td %TH:%TM:%TS %p\\n' 2>/dev/null | sort -r | head -80"
        )
        commands.append(
            f"echo '=== RECENT OUT ==='; find {shlex.quote(BASE)} -maxdepth 4 -type f -name '*.out' "
            "-printf '%T@ %p\\n' 2>/dev/null | sort -nr | head -15 | cut -d' ' -f2- | "
            "while IFS= read -r f; do echo ---$f; tail -80 \"$f\" | "
            "grep -E 'Time Step|Numerical Instability|ERROR|STOP: FDS completed successfully' | tail -3; done"
        )
        commands.append(
            f"echo '=== QUEUE JSON ==='; for f in {shlex.quote(BASE)}/queue/node0{{1,3,4,5}}_status.json; "
            "do echo ---$f; cat \"$f\" 2>/dev/null; echo; done"
        )
        for relative in ACTIVE_CASES:
            case_dir = f"{BASE}/{relative}"
            commands.append(
                f"echo '=== CASE {relative} ==='; "
                f"f=$(find {shlex.quote(case_dir)} -maxdepth 1 -name '*_devc.csv' | head -1); "
                "echo DEVC=$f; test -n \"$f\" && tail -1 \"$f\"; "
                f"o=$(find {shlex.quote(case_dir)} -maxdepth 1 -name '*.out' | head -1); "
                "echo OUT=$o; test -n \"$o\" && grep -E 'Numerical Instability|ERROR|STOP: FDS completed successfully' \"$o\" | tail -5; "
                f"test -f {shlex.quote(case_dir + '/damage_assessment.json')} && "
                f"python3 -c \"import json; d=json.load(open('{case_dir}/damage_assessment.json')); "
                "print('ASSESS',d.get('sim_t_s'),d.get('severe_count'),d.get('total_count'),d.get('aircraft_level'),d.get('evaluation_status'))\""
            )
        command = "; ".join(commands)
        _, stdout, stderr = client.exec_command(command, timeout=90)
        print(stdout.read().decode("utf-8", errors="replace"))
        error = stderr.read().decode("utf-8", errors="replace").strip()
        if error:
            print("REMOTE_STDERR:", error)
    finally:
        client.close()


if __name__ == "__main__":
    main()

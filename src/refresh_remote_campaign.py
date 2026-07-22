#!/usr/bin/env python3
"""Refresh remote live assessments and print a compact campaign snapshot."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import paramiko


CONFIG = Path(r"D:\Pyrosim\radiation_ignition_damage_workflow_20260716\gui_windows\user_config.json")
BASE = "/home/zsh/FDS/FDS6/radiation_ignition_damage_workflow_20260720_H1_H7"
CASES = (
    "Q0050_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRupper_thickness_audit",
    "Q0200_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRupper_thickness_audit",
    "Q0400_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRupper_thickness_audit",
    "Q0200_W0100_az060_el75_H1H7_v5_Qnorm_adapt_HRRupper_thickness_audit_angle",
)


def sync_outputs(client: paramiko.SSHClient) -> None:
    local_root = Path(__file__).resolve().parents[1]
    sftp = client.open_sftp()
    try:
        files = []
        for case in CASES:
            for name in ("damage_assessment.json", "damage_assessment.md", "damage_tree.svg"):
                files.append(f"cases_adaptive/{case}/{name}")
        files.extend((
            "reports/completed_case_damage_tree_assessments.md",
            "reports/live_HRRupper_thickness_damage_monitor.md",
        ))
        remote_plot_dir = f"{BASE}/outputs/live_HRRupper_thickness_monitor"
        try:
            for item in sftp.listdir_attr(remote_plot_dir):
                if stat.S_ISREG(item.st_mode):
                    files.append(f"outputs/live_HRRupper_thickness_monitor/{item.filename}")
        except OSError:
            pass
        for relative in files:
            local = local_root / Path(relative)
            local.parent.mkdir(parents=True, exist_ok=True)
            try:
                sftp.get(f"{BASE}/{relative}", str(local))
            except OSError as exc:
                print(f"SYNC_SKIPPED {relative}: {exc}")
        print(f"SYNCED {len(files)} selected artifacts")
    finally:
        sftp.close()


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
        commands = [f"cd '{BASE}'"]
        for case in CASES:
            commands.append(
                f"/usr/bin/python3.11 src/assess_results.py 'cases_adaptive/{case}' "
                f">/tmp/assess_{case}.log 2>&1 || "
                f"{{ echo ASSESS_FAILED:{case}; tail -20 /tmp/assess_{case}.log; }}"
            )
        commands.extend((
            "/usr/bin/python3.11 src/plot_live_temperature_hrr_heatflux.py >/tmp/live_plots.log 2>&1 || "
            "{ echo PLOT_FAILED; tail -30 /tmp/live_plots.log; }",
            "/usr/bin/python3.11 src/update_live_campaign_report.py >/tmp/live_report.log 2>&1 || "
            "{ echo REPORT_FAILED; tail -30 /tmp/live_report.log; }",
        ))
        for case in CASES:
            path = f"{BASE}/cases_adaptive/{case}/damage_assessment.json"
            code = (
                "import json;d=json.load(open('" + path + "'));"
                "eq=d.get('equipment',{});"
                "keys=['SEAT','BED','CURT','WINS','RADM','U4','H1','H2','H3','H4','H5','H6','H7'];"
                "print(json.dumps({'case':d.get('case'),'sim_t_s':d.get('sim_t_s'),"
                "'status':d.get('evaluation_status'),'severe':d.get('severe_count'),"
                "'total':d.get('total_count'),'aircraft':d.get('aircraft_level'),"
                "'groups':{k:{'level':eq.get(k,{}).get('level'),'peak_C':eq.get(k,{}).get('peak_C'),"
                "'severe_continuous_s':eq.get(k,{}).get('criteria',{}).get('severe',{}).get('continuous_s')} "
                "for k in keys}},ensure_ascii=False))"
            )
            commands.append(f"/usr/bin/python3.11 -c \"{code}\"")
        _, stdout, stderr = client.exec_command("; ".join(commands), timeout=300)
        print(stdout.read().decode("utf-8", errors="replace"))
        error = stderr.read().decode("utf-8", errors="replace").strip()
        if error:
            print("REMOTE_STDERR:", error)
        sync_outputs(client)
    finally:
        client.close()


if __name__ == "__main__":
    main()

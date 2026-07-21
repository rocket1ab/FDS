#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CRITERIA = json.loads((ROOT / "config" / "damage_criteria.json").read_text(encoding="utf-8"))["groups"]
TREE = json.loads((ROOT / "config" / "damage_tree.json").read_text(encoding="utf-8"))
EXCLUDED_PROBES = set(json.loads(
    (ROOT / "config" / "excluded_probe_ids_v5.json").read_text(encoding="utf-8")
)["wall_temperature_ids"])
ORDER = {"unknown": -1, "none": 0, "mild": 1, "moderate": 2, "severe": 3}


def read_devc(path: Path):
    rows = list(csv.reader(path.open(encoding="utf-8-sig", errors="replace")))
    header_index = next(i for i, row in enumerate(rows) if row and row[0].strip().strip('"').lower() == "time")
    header = [cell.strip().strip('"') for cell in rows[header_index]]
    columns = {name: [] for name in header}
    for row in rows[header_index + 1:]:
        if len(row) < len(header):
            continue
        for name, value in zip(header, row):
            try:
                columns[name].append(float(value))
            except ValueError:
                columns[name].append(float("nan"))
    return columns


def envelope(columns: dict, names: list[str], n: int):
    result = []
    active = []
    for i in range(n):
        values = [(name, columns.get(name, [float("nan")] * n)[i]) for name in names]
        values = [(name, value) for name, value in values if math.isfinite(value)]
        if values:
            name, value = max(values, key=lambda item: item[1])
            result.append(value)
            active.append(name)
        else:
            result.append(float("nan"))
            active.append(None)
    return result, active


def longest_above(times, values, threshold):
    best = 0.0
    start = None
    for time, value in zip(times, values):
        if math.isfinite(value) and value >= threshold:
            start = time if start is None else start
            best = max(best, time - start)
        else:
            start = None
    return best


def system_level(spec: dict, equipment: dict):
    major = [(name, equipment.get(name, {}).get("level", "unknown")) for name in spec["major"]]
    secondary = [(name, equipment.get(name, {}).get("level", "unknown")) for name in spec["secondary"]]
    if any(level == "severe" for _, level in major):
        return "severe"
    if any(level == "moderate" for _, level in major + secondary) or any(level == "severe" for _, level in secondary):
        return "moderate"
    if any(level == "mild" for _, level in major + secondary):
        return "mild"
    known = [level for _, level in major + secondary if level != "unknown"]
    return "none" if known and len(known) == len(major + secondary) else "unknown"


def assess(case_dir: Path):
    summary = json.loads((case_dir / "case_summary.json").read_text(encoding="utf-8"))
    registry = json.loads((case_dir / "monitor_registry.json").read_text(encoding="utf-8"))
    excluded_for_case = EXCLUDED_PROBES if "_v5_Qnorm" in summary["case"] else set()
    devc = next(case_dir.glob("*_devc.csv"), None)
    if not devc:
        raise FileNotFoundError("No DEVC CSV")
    columns = read_devc(devc)
    times = columns.get("Time", [])
    equipment = {}
    for group, criteria in CRITERIA.items():
        names = [
            item["wt"] for item in registry.get(group, [])
            if item["wt"] in columns and item["wt"] not in excluded_for_case
        ]
        excluded = [item["wt"] for item in registry.get(group, []) if item["wt"] in excluded_for_case]
        if not names or not times:
            equipment[group] = {"level": "unknown", "reason": "missing_probe_data"}
            continue
        values, active = envelope(columns, names, len(times))
        finite = [value for value in values if math.isfinite(value)]
        peak = max(finite) if finite else float("nan")
        level = "none"
        evidence = {}
        for tier in ("mild", "moderate", "severe"):
            temperature, duration = criteria[tier]
            continuous = longest_above(times, values, temperature)
            evidence[tier] = {"temperature_C": temperature, "required_s": duration, "continuous_s": continuous}
            if peak >= temperature and continuous >= duration:
                level = tier
        switches = sum(a != b for a, b in zip(active, active[1:]) if a and b)
        equipment[group] = {"label": criteria["label"], "level": level, "peak_C": peak,
                            "probe_count": len(names), "dynamic_probe_switches": switches,
                            "excluded_invalid_probes": excluded,
                            "evidence": evidence}
    systems = {name: system_level(spec, equipment) for name, spec in TREE["systems"].items()}
    known_systems = [level for level in systems.values() if level != "unknown"]
    aircraft = max(known_systems, key=ORDER.get) if known_systems else "unknown"
    severe = sum(item["level"] == "severe" for item in equipment.values())
    result = {"case": summary["case"], "Q_J_cm2": summary["Q_J_cm2"],
              "sim_t_s": times[-1] if times else 0, "equipment": equipment,
              "severe_count": severe, "total_count": len(CRITERIA),
              "severe_ratio": severe / len(CRITERIA), "all_severe": severe == len(CRITERIA),
              "excluded_invalid_probe_ids": sorted(excluded_for_case),
              "maximum_temperature_definition": "maximum dynamic envelope of geometrically valid WT probes",
              "boundary_field_available": True,
              "systems": systems, "aircraft_level": aircraft}
    (case_dir / "damage_assessment.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# Damage assessment: {summary['case']}", "", f"Severe: **{severe}/{len(CRITERIA)}**", "",
             "| Group | Level | Peak (C) | Probes |", "|---|---:|---:|---:|"]
    for group, item in equipment.items():
        lines.append(f"| {group} | {item['level']} | {item.get('peak_C', float('nan')):.1f} | {item.get('probe_count', 0)} |")
    (case_dir / "damage_assessment.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    update_threshold_summary()
    return result


def update_threshold_summary():
    results = []
    for path in sorted((ROOT / "cases").glob("*/damage_assessment.json")):
        results.append(json.loads(path.read_text(encoding="utf-8")))
    results.sort(key=lambda item: item["Q_J_cm2"])
    successes = [item for item in results if item["all_severe"]]
    failures = [item for item in results if not item["all_severe"]]
    summary = {"completed_cases": len(results), "results": [{"Q": r["Q_J_cm2"], "severe": r["severe_count"],
                "total": r["total_count"], "all_severe": r["all_severe"]} for r in results],
               "first_all_severe_Q": min((r["Q_J_cm2"] for r in successes), default=None),
               "last_not_all_severe_Q": max((r["Q_J_cm2"] for r in failures), default=None)}
    if len(results) == 5 and not successes:
        summary["next_action"] = "expand_above_400"
    elif successes:
        lower = max((r["Q_J_cm2"] for r in failures if r["Q_J_cm2"] < summary["first_all_severe_Q"]), default=0)
        summary["threshold_bracket_J_cm2"] = [lower, summary["first_all_severe_Q"]]
    (ROOT / "threshold_status.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    print(json.dumps(assess(Path(sys.argv[1]).resolve()), ensure_ascii=False, indent=2))

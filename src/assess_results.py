#!/usr/bin/env python3
from __future__ import annotations

import csv
import html
import json
import math
import os
import re
import sys
from datetime import datetime
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


def system_evidence(spec: dict, equipment: dict):
    major = {name: equipment.get(name, {}).get("level", "unknown") for name in spec["major"]}
    secondary = {name: equipment.get(name, {}).get("level", "unknown") for name in spec["secondary"]}
    level = system_level(spec, equipment)
    if level == "severe":
        triggers = [name for name, value in major.items() if value == "severe"]
        rule = "at least one major item is severe"
    elif level == "moderate":
        triggers = [name for name, value in major.items() if value == "moderate"]
        triggers += [name for name, value in secondary.items() if value in {"moderate", "severe"}]
        rule = "a major item is moderate or a secondary item is severe"
    elif level == "mild":
        triggers = [name for name, value in {**major, **secondary}.items() if value == "mild"]
        rule = "at least one known item is mild and no higher rule is met"
    elif level == "none":
        triggers = []
        rule = "all mapped items are known and none is damaged"
    else:
        triggers = [name for name, value in {**major, **secondary}.items() if value == "unknown"]
        rule = "evidence is missing for at least one mapped item"
    return {"level": level, "major": major, "secondary": secondary,
            "triggers": triggers, "rule": rule}


LEVEL_COLORS = {
    "unknown": ("#f1f3f5", "#495057"),
    "none": ("#e9ecef", "#343a40"),
    "mild": ("#fff3bf", "#7a5b00"),
    "moderate": ("#ffd8a8", "#8a3b00"),
    "severe": ("#ffc9c9", "#a51111"),
}


def render_tree_svg(result: dict, path: Path):
    specs = TREE["systems"]
    columns = list(specs)
    width = 1480
    margin = 28
    gap = 18
    column_width = (width - 2 * margin - gap * (len(columns) - 1)) / len(columns)
    root_y, system_y, item_y = 24, 132, 258
    box_h, item_h, item_gap = 64, 56, 12
    max_items = max(len(specs[name]["major"]) + len(specs[name]["secondary"]) for name in columns)
    height = int(item_y + max_items * (item_h + item_gap) + 92)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",Arial,sans-serif;letter-spacing:0}.title{font-size:20px;font-weight:700}.label{font-size:15px;font-weight:600}.small{font-size:12px}.line{stroke:#6c757d;stroke-width:2;fill:none}</style>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]

    def box(x, y, w, h, title, level, subtitle=""):
        fill, stroke = LEVEL_COLORS.get(level, LEVEL_COLORS["unknown"])
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="4" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        title_y = y + (25 if h >= 60 else 23)
        subtitle_y = y + h - 11
        parts.append(f'<text x="{x + w / 2:.1f}" y="{title_y:.1f}" text-anchor="middle" class="label" fill="#212529">{html.escape(title)}</text>')
        parts.append(f'<text x="{x + w / 2:.1f}" y="{subtitle_y:.1f}" text-anchor="middle" class="small" fill="{stroke}">{html.escape(level.upper() + (" | " + subtitle if subtitle else ""))}</text>')

    root_w = 360
    root_x = (width - root_w) / 2
    box(root_x, root_y, root_w, box_h, "Aircraft target / 飞机目标", result["aircraft_level"], "PDF tree level")
    parts.append(f'<path class="line" d="M {width / 2:.1f} {root_y + box_h:.1f} V {system_y - 28:.1f}"/>')
    first_center = margin + column_width / 2
    last_center = width - margin - column_width / 2
    parts.append(f'<path class="line" d="M {first_center:.1f} {system_y - 28:.1f} H {last_center:.1f}"/>')

    for index, name in enumerate(columns):
        spec = specs[name]
        x = margin + index * (column_width + gap)
        center = x + column_width / 2
        parts.append(f'<path class="line" d="M {center:.1f} {system_y - 28:.1f} V {system_y:.1f}"/>')
        box(x, system_y, column_width, box_h, spec.get("label", name), result["systems"].get(name, "unknown"), name)
        parts.append(f'<path class="line" d="M {center:.1f} {system_y + box_h:.1f} V {item_y - 16:.1f}"/>')
        items = [(group, "major") for group in spec["major"]] + [(group, "secondary") for group in spec["secondary"]]
        for row, (group, role) in enumerate(items):
            y = item_y + row * (item_h + item_gap)
            item = result["equipment"].get(group, {"level": "unknown"})
            title = f'{group}  {item.get("label", group)}'
            box(x + 10, y, column_width - 20, item_h, title, item.get("level", "unknown"), role)
            if row == 0:
                parts.append(f'<path class="line" d="M {center:.1f} {item_y - 16:.1f} V {y:.1f}"/>')
            else:
                previous = item_y + (row - 1) * (item_h + item_gap) + item_h
                parts.append(f'<path class="line" d="M {center:.1f} {previous:.1f} V {y:.1f}"/>')

    legend_y = height - 42
    lx = margin
    for level in ("unknown", "none", "mild", "moderate", "severe"):
        fill, stroke = LEVEL_COLORS[level]
        parts.append(f'<rect x="{lx}" y="{legend_y}" width="22" height="18" fill="{fill}" stroke="{stroke}"/>')
        parts.append(f'<text x="{lx + 30}" y="{legend_y + 14}" class="small">{level}</text>')
        lx += 128
    parts.append(f'<text x="{width - margin}" y="{legend_y + 14}" text-anchor="end" class="small">Strict all-severe: {result["severe_count"]}/{result["total_count"]}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def evidence_cell(item: dict, tier: str):
    evidence = item.get("evidence", {}).get(tier, {})
    if not evidence:
        return "-"
    return (f'{evidence.get("temperature_C", 0):g} C; '
            f'{evidence.get("continuous_s", 0):.1f}/{evidence.get("required_s", 0):g} s')


def case_markdown(result: dict, image_ref: str):
    lines = [
        f'# Complete damage-tree assessment: {result["case"]}', "",
        f'- Simulation time: **{result["sim_t_s"]:.2f} s**',
        f'- Source directory: `{result.get("case_directory", "unknown")}`',
        f'- Campaign classification: **{result.get("campaign_classification", "unclassified")}**',
        f'- PDF aircraft-tree level: **{result["aircraft_level"].upper()}**',
        f'- Strict all-equipment severe result: **{result["severe_count"]}/{result["total_count"]}** '
        f'(`all_severe={str(result["all_severe"]).lower()}`)',
        '- Maximum temperature: dynamic envelope of geometrically valid redundant wall-temperature probes.',
        '- Important: the strict 17/17 metric is not the PDF aircraft-level rule.', "",
        '## Damage tree', "", f'![Damage tree]({image_ref})', "",
        '## System propagation', "",
        '| System | Level | Trigger nodes | Applied rule |',
        '|---|---:|---|---|',
    ]
    for name, detail in result["system_evidence"].items():
        label = TREE["systems"][name].get("label", name)
        triggers = ", ".join(detail["triggers"]) or "none"
        lines.append(f'| {label} (`{name}`) | {detail["level"]} | {triggers} | {detail["rule"]} |')
    lines += ["", "## Complete equipment assessment", "",
              '| Group | Equipment | Role | Level | Peak C | Mild evidence | Moderate evidence | Severe evidence | Valid probes |',
              '|---|---|---|---:|---:|---|---|---|---:|']
    roles = {}
    for system, spec in TREE["systems"].items():
        for group in spec["major"]:
            roles[group] = f'{system}:major'
        for group in spec["secondary"]:
            roles[group] = f'{system}:secondary'
    for group, item in result["equipment"].items():
        lines.append(
            f'| {group} | {item.get("label", group)} | {roles.get(group, "unmapped")} | '
            f'{item.get("level", "unknown")} | {item.get("peak_C", float("nan")):.1f} | '
            f'{evidence_cell(item, "mild")} | {evidence_cell(item, "moderate")} | '
            f'{evidence_cell(item, "severe")} | {item.get("probe_count", 0)} |'
        )
    not_severe = [group for group, item in result["equipment"].items() if item.get("level") != "severe"]
    lines += ["", "## Assessment interpretation", "",
              f'- Non-severe or unknown groups: **{", ".join(not_severe) if not_severe else "none"}**.',
              f'- Aircraft level is propagated from the highest system level: **{result["aircraft_level"]}**.',
              '- H2 (mission) and H3 (display) are model-specific mappings; their generic electronics thresholds are not same-name PDF rows.',
              '- H1-H4 probes currently measure aluminium enclosure surface temperature as a proxy for internal electronics temperature.', ""]
    return "\n".join(lines)


def update_campaign_damage_report():
    results = []
    for path in ROOT.glob("cases*/*/damage_assessment.json"):
        logs = [path.parent / "run.log", *path.parent.glob("*.out")]
        normal_completion = False
        for log in logs:
            if not log.exists():
                continue
            text = log.read_text(encoding="utf-8", errors="replace")
            if "STOP: FDS completed successfully" in text and "Numerical Instability" not in text:
                normal_completion = True
                break
        if not normal_completion:
            continue
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if "system_evidence" not in item and "equipment" in item:
            details = {
                name: system_evidence(spec, item["equipment"])
                for name, spec in TREE["systems"].items()
            }
            item["system_evidence"] = details
            item["systems"] = {name: detail["level"] for name, detail in details.items()}
            known = [level for level in item["systems"].values() if level != "unknown"]
            item["aircraft_level"] = max(known, key=ORDER.get) if known else "unknown"
        case_rel = path.parent.relative_to(ROOT).as_posix()
        family = case_rel.split("/", 1)[0]
        classifications = {
            "cases_qnorm": "corrected Q-normalized baseline",
            "cases_probe_corrected": "probe-corrected sensitivity",
            "cases_adaptive": "adaptive sensitivity; compare separately",
            "cases_threshold": "threshold-search case",
            "cases_legacy_stable": "retired legacy-flux provenance",
            "cases_stable": "retired numerical diagnostic",
            "cases_exploratory": "corrected Q-normalized exploratory baseline",
            "cases": "developmental provenance",
        }
        item["case_directory"] = case_rel
        item["campaign_classification"] = classifications.get(family, family)
        render_tree_svg(item, path.parent / "damage_tree.svg")
        (path.parent / "damage_assessment.md").write_text(
            case_markdown(item, "damage_tree.svg") + "\n", encoding="utf-8"
        )
        item["_assessment_path"] = path
        results.append(item)
    results.sort(key=lambda item: (item.get("Q_J_cm2", float("inf")), item.get("case", "")))
    lines = ["# Completed-case damage-tree assessments", "",
             "Automatically rebuilt after every successful FDS run and assessment.", "",
             "| Case | Campaign | Q (J/cm2) | Sim time (s) | PDF aircraft level | Strict severe |",
             "|---|---|---:|---:|---:|---:|"]
    for item in results:
        lines.append(f'| {item["case"]} | {item.get("campaign_classification", "unclassified")} | '
                     f'{item.get("Q_J_cm2", float("nan")):g} | '
                     f'{item.get("sim_t_s", 0):.1f} | {item.get("aircraft_level", "unknown")} | '
                     f'{item.get("severe_count", 0)}/{item.get("total_count", 0)} |')
    for item in results:
        assessment_path = item.pop("_assessment_path")
        case_rel = assessment_path.parent.relative_to(ROOT).as_posix()
        lines += ["", "---", "", case_markdown(item, f'../{case_rel}/damage_tree.svg').replace("# Complete", "## Complete", 1)]
    report = ROOT / "reports" / "completed_case_damage_tree_assessments.md"
    temp = report.with_name(f".{report.name}.{os.getpid()}.tmp")
    temp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temp.replace(report)


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
    details = {name: system_evidence(spec, equipment) for name, spec in TREE["systems"].items()}
    systems = {name: detail["level"] for name, detail in details.items()}
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
              "systems": systems, "system_evidence": details, "aircraft_level": aircraft,
              "assessment_standard": TREE["interpretation"]["source"],
              "assessed_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    (case_dir / "damage_assessment.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    render_tree_svg(result, case_dir / "damage_tree.svg")
    (case_dir / "damage_assessment.md").write_text(
        case_markdown(result, "damage_tree.svg") + "\n", encoding="utf-8"
    )
    update_campaign_damage_report()
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

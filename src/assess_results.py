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


def severe_conclusion(item: dict):
    evidence = item.get("evidence", {}).get("severe")
    if not evidence:
        return "Unknown: severe-threshold evidence is missing"
    threshold = evidence.get("temperature_C", float("nan"))
    required = evidence.get("required_s", float("nan"))
    continuous = evidence.get("continuous_s", 0.0)
    peak = item.get("peak_C", float("nan"))
    if item.get("level") == "severe":
        return f"Reached: peak {peak:.1f} C; >= {threshold:g} C for {continuous:.1f}/{required:g} s"
    if not math.isfinite(peak):
        return "Unknown: no finite valid-probe temperature"
    if peak < threshold:
        return f"Not reached: peak {peak:.1f} C < {threshold:g} C"
    return f"Not reached: duration above {threshold:g} C is {continuous:.1f}/{required:g} s"


def physical_interpretation(item: dict):
    evidence = item.get("evidence", {}).get("severe", {})
    peak = item.get("peak_C", float("nan"))
    threshold = evidence.get("temperature_C", float("inf"))
    continuous = evidence.get("continuous_s", 0.0)
    required = evidence.get("required_s", float("inf"))
    direct = item.get("positive_external_flux_probe_count", 0)
    if item.get("level") == "unknown":
        return "Probe evidence is missing; no physical conclusion is valid."
    if item.get("level") == "severe":
        source = "direct-flux and/or fire heating" if direct else "secondary cabin-fire heating"
        return f"The {source} supplied both sufficient temperature and duration."
    if peak < threshold:
        if direct:
            return "Positive external flux reaches monitored faces, but pulse energy, thermal inertia and heat losses keep the peak below severe threshold."
        return "No monitored face has positive assigned external flux; geometric shielding leaves secondary cabin-fire heating below severe threshold."
    if continuous < required:
        return "A transient flash/fire peak crosses the severe temperature, but combustion or heat feedback is not sustained for the required duration."
    return "The severe criterion is not met for an unresolved evidence combination."


def case_configuration(case_dir: Path, summary: dict):
    fds = next(case_dir.glob("*.fds"), None)
    text = fds.read_text(encoding="utf-8", errors="replace") if fds else ""

    def number(pattern, default=None):
        match = re.search(pattern, text, flags=re.I | re.S)
        return float(match.group(1)) if match else default

    hrrpua = sorted({float(value) for value in re.findall(r"\bHRRPUA\s*=\s*([-+0-9.Ee]+)", text, flags=re.I)})
    thicknesses = sorted({float(value) for value in re.findall(r"\bTHICKNESS\(1\)\s*=\s*([-+0-9.Ee]+)", text, flags=re.I)})
    return {
        "purpose": summary.get("purpose", "unspecified"),
        "source_case": summary.get("source_case"),
        "changed_factor": summary.get("changed_factor", "none recorded"),
        "Q_J_cm2": summary.get("Q_J_cm2"),
        "yield_kt": summary.get("yield_kt"),
        "azimuth_deg": summary.get("azimuth_deg"),
        "elevation_deg": summary.get("elevation_deg"),
        "target_t_end_s": summary.get("t_end_s", number(r"&TIME\b[^/]*\bT_END\s*=\s*([-+0-9.Ee]+)")),
        "mpi_processes": summary.get("mpi"),
        "burn_away": summary.get("burn_away", bool(re.search(r"\bBURN_AWAY\s*=\s*\.TRUE\.", text, flags=re.I))),
        "radiative_fraction": number(r"\bRADIATIVE_FRACTION\s*=\s*([-+0-9.Ee]+)"),
        "cfl_max": number(r"\bCFL_MAX\s*=\s*([-+0-9.Ee]+)"),
        "time_step_dt_s": number(r"&TIME\b[^/]*\bDT\s*=\s*([-+0-9.Ee]+)"),
        "nuclear_ramp_integral_s": summary.get("nuclear_ramp_integral_s"),
        "plane_peak_irradiance_kw_m2": summary.get("plane_peak_irradiance_kw_m2"),
        "max_local_external_flux_kw_m2": summary.get("max_local_external_flux_kw_m2"),
        "max_local_fluence_J_cm2": summary.get("max_local_fluence_J_cm2"),
        "hrrpua_group_values_kw_m2": summary.get("hrrpua_kW_m2"),
        "all_hrrpua_values_in_fds_kw_m2": hrrpua,
        "audited_group_thickness_m": summary.get("thickness_m"),
        "all_layer_thicknesses_in_fds_m": thicknesses,
        "geometry_changed": summary.get("geometry_changed", False),
        "materials_changed": summary.get("materials_changed", False),
        "combustion_changed": summary.get("combustion_changed", False),
        "external_flux_changed": summary.get("external_flux_changed", False),
        "ignition_temperature_changed": summary.get("ignition_temperature_changed", False),
        "damage_thresholds_changed": summary.get("damage_thresholds_changed", False),
        "fds_input": fds.name if fds else None,
    }


def result_issues(result: dict):
    issues = []
    status = result.get("evaluation_status", "unknown")
    if status != "normal_completion":
        issues.append(
            f'Long-duration snapshot at {result.get("sim_t_s", 0):.1f} s without a normal FDS completion marker; '
            "temperatures and levels can still change before T_END."
        )
    classification = result.get("campaign_classification", "")
    if "retired" in classification or "provenance" in classification:
        issues.append("This is a retired/provenance configuration and is excluded from the current threshold bracket.")
    config = result.get("configuration", {})
    q = config.get("Q_J_cm2")
    local_q = config.get("max_local_fluence_J_cm2")
    if q and local_q is not None and local_q < 0.8 * q:
        issues.append(f"Maximum local integrated fluence is only {local_q:.3g} J/cm2 for nominal Q={q:g}; normalization/exposure must be considered.")
    if config.get("damage_thresholds_changed"):
        issues.append("Damage thresholds differ from the fixed standard, so this case is not threshold-comparable.")
    issues.append("H1-H4 use aluminium-enclosure wall temperature as a proxy for internal electronics temperature.")
    return issues


def format_config_value(value):
    if value is None:
        return "not recorded"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def evaluation_status(case_dir: Path, sim_t_s: float):
    logs = [case_dir / "run.log", *case_dir.glob("*.out")]
    combined = ""
    for log in logs:
        if log.exists():
            combined += log.read_text(encoding="utf-8", errors="replace")
    if "STOP: FDS completed successfully" in combined and "Numerical Instability" not in combined:
        return "normal_completion"
    if "Numerical Instability" in combined:
        return "long_snapshot_with_numerical_instability" if sim_t_s >= 1000 else "invalid_numerical_instability"
    if sim_t_s >= 1000:
        return "long_duration_snapshot_without_normal_stop"
    return "insufficient_duration_snapshot"


def case_markdown(result: dict, image_ref: str):
    lines = [
        f'# Complete damage-tree assessment: {result["case"]}', "",
        f'- Simulation time: **{result["sim_t_s"]:.2f} s**',
        f'- Source directory: `{result.get("case_directory", "unknown")}`',
        f'- Campaign classification: **{result.get("campaign_classification", "unclassified")}**',
        f'- Evaluation status: **{result.get("evaluation_status", "unknown")}**',
        f'- PDF aircraft-tree level: **{result["aircraft_level"].upper()}**',
        f'- Strict all-equipment severe result: **{result["severe_count"]}/{result["total_count"]}** '
        f'(`all_severe={str(result["all_severe"]).lower()}`)',
        '- Maximum temperature: dynamic envelope of geometrically valid redundant wall-temperature probes.',
        '- Important: the strict 17/17 metric is not the PDF aircraft-level rule.', "",
        '## Case configuration', "",
        '| Parameter | Value |', '|---|---|',
    ]
    config_order = (
        "purpose", "source_case", "changed_factor", "Q_J_cm2", "yield_kt", "azimuth_deg",
        "elevation_deg", "target_t_end_s", "mpi_processes", "burn_away", "radiative_fraction",
        "cfl_max", "time_step_dt_s", "nuclear_ramp_integral_s", "plane_peak_irradiance_kw_m2",
        "max_local_external_flux_kw_m2", "max_local_fluence_J_cm2", "hrrpua_group_values_kw_m2",
        "all_hrrpua_values_in_fds_kw_m2", "audited_group_thickness_m",
        "all_layer_thicknesses_in_fds_m", "geometry_changed", "materials_changed",
        "combustion_changed", "external_flux_changed", "ignition_temperature_changed",
        "damage_thresholds_changed", "fds_input",
    )
    for key in config_order:
        value = format_config_value(result.get("configuration", {}).get(key)).replace("|", "\\|")
        lines.append(f'| `{key}` | {value} |')
    lines += ["", "## Known issues and validity", ""]
    for issue in result_issues(result):
        lines.append(f'- {issue}')
    lines += ["", '## Damage tree', "", f'![Damage tree]({image_ref})', "",
        '## System propagation', "",
        '| System | Level | Trigger nodes | Applied rule |',
        '|---|---:|---|---|',
    ]
    for name, detail in result["system_evidence"].items():
        label = TREE["systems"][name].get("label", name)
        triggers = ", ".join(detail["triggers"]) or "none"
        lines.append(f'| {label} (`{name}`) | {detail["level"]} | {triggers} | {detail["rule"]} |')
    lines += ["", "## Complete equipment assessment", "",
              '| Group | Equipment | Role | Level | Peak C | Mild evidence | Moderate evidence | Severe evidence | Severe conclusion | Physical interpretation | Positive-flux probes | Valid probes |',
              '|---|---|---|---:|---:|---|---|---|---|---|---:|---:|']
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
            f'{evidence_cell(item, "severe")} | {severe_conclusion(item)} | '
            f'{physical_interpretation(item)} | {item.get("positive_external_flux_probe_count", 0)} | '
            f'{item.get("probe_count", 0)} |'
        )
    not_severe = [group for group, item in result["equipment"].items() if item.get("level") != "severe"]
    peak_shortfall = sum(
        item.get("peak_C", float("-inf")) < item.get("evidence", {}).get("severe", {}).get("temperature_C", float("inf"))
        for item in result["equipment"].values() if item.get("level") != "severe"
    )
    duration_shortfall = sum(
        item.get("peak_C", float("-inf")) >= item.get("evidence", {}).get("severe", {}).get("temperature_C", float("inf"))
        and item.get("evidence", {}).get("severe", {}).get("continuous_s", 0) < item.get("evidence", {}).get("severe", {}).get("required_s", float("inf"))
        for item in result["equipment"].values() if item.get("level") != "severe"
    )
    lines += ["", "## Assessment interpretation", "",
              f'- Non-severe or unknown groups: **{", ".join(not_severe) if not_severe else "none"}**.',
              f'- Severe-damage shortfalls: **{peak_shortfall} peak-temperature limited**, **{duration_shortfall} duration limited**.',
              f'- Aircraft level is propagated from the highest system level: **{result["aircraft_level"]}**.',
              '- H2 (mission) and H3 (display) are model-specific mappings; their generic electronics thresholds are not same-name PDF rows.',
              '- H1-H4 probes currently measure aluminium enclosure surface temperature as a proxy for internal electronics temperature.', ""]
    return "\n".join(lines)


def update_campaign_damage_report():
    results = []
    for path in ROOT.glob("cases*/*/damage_assessment.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        status = evaluation_status(path.parent, item.get("sim_t_s", 0))
        if status in {"insufficient_duration_snapshot", "invalid_numerical_instability"}:
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
        item["evaluation_status"] = status
        summary_path = path.parent / "case_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
        item["configuration"] = case_configuration(path.parent, summary)
        render_tree_svg(item, path.parent / "damage_tree.svg")
        (path.parent / "damage_assessment.md").write_text(
            case_markdown(item, "damage_tree.svg") + "\n", encoding="utf-8"
        )
        path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        item["_assessment_path"] = path
        results.append(item)
    results.sort(key=lambda item: (item.get("Q_J_cm2", float("inf")), item.get("case", "")))
    lines = ["# Long-duration and completed damage-tree assessments", "",
             "Automatically rebuilt after assessment. It includes normal FDS completions and explicitly labeled snapshots at or beyond 1000 s.", "",
             "| Case | Status | Campaign | Q (J/cm2) | Sim time (s) | PDF aircraft level | Strict severe |",
             "|---|---|---|---:|---:|---:|---:|"]
    for item in results:
        lines.append(f'| {item["case"]} | {item.get("evaluation_status", "unknown")} | '
                     f'{item.get("campaign_classification", "unclassified")} | '
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
        registered = registry.get(group, [])
        positive_flux = [item for item in registered if float(item.get("base_flux", 0) or 0) > 0]
        equipment[group] = {"label": criteria["label"], "level": level, "peak_C": peak,
                            "probe_count": len(names), "dynamic_probe_switches": switches,
                            "positive_external_flux_probe_count": len(positive_flux),
                            "max_registered_external_flux_kw_m2": max(
                                (float(item.get("base_flux", 0) or 0) for item in positive_flux), default=0.0
                            ),
                            "excluded_invalid_probes": excluded,
                            "evidence": evidence}
    details = {name: system_evidence(spec, equipment) for name, spec in TREE["systems"].items()}
    systems = {name: detail["level"] for name, detail in details.items()}
    known_systems = [level for level in systems.values() if level != "unknown"]
    aircraft = max(known_systems, key=ORDER.get) if known_systems else "unknown"
    severe = sum(item["level"] == "severe" for item in equipment.values())
    sim_t_s = times[-1] if times else 0
    result = {"case": summary["case"], "Q_J_cm2": summary["Q_J_cm2"],
              "sim_t_s": sim_t_s, "equipment": equipment,
              "severe_count": severe, "total_count": len(CRITERIA),
              "severe_ratio": severe / len(CRITERIA), "all_severe": severe == len(CRITERIA),
              "excluded_invalid_probe_ids": sorted(excluded_for_case),
              "maximum_temperature_definition": "maximum dynamic envelope of geometrically valid WT probes",
              "boundary_field_available": True,
              "systems": systems, "system_evidence": details, "aircraft_level": aircraft,
              "evaluation_status": evaluation_status(case_dir, sim_t_s),
              "configuration": case_configuration(case_dir, summary),
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

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
CRITERIA_DOC = json.loads((ROOT / "config" / "damage_criteria.json").read_text(encoding="utf-8"))
CRITERIA = CRITERIA_DOC["groups"]
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


def probe_validity(times, columns, names):
    """Describe trailing probe loss without turning missing samples into cooling."""
    if not times:
        return {}
    positive_steps = [
        later - earlier for earlier, later in zip(times, times[1:])
        if later > earlier
    ]
    tolerance = max(2.0 * (positive_steps[-1] if positive_steps else 0.0), 1.0e-6)
    result = {}
    for name in names:
        values = columns.get(name, [])
        valid = [
            index for index, value in enumerate(values[:len(times)])
            if math.isfinite(value)
        ]
        last_valid = times[valid[-1]] if valid else None
        result[name] = {
            "valid_sample_count": len(valid),
            "last_valid_time_s": last_valid,
            "trailing_dropout": bool(
                valid and last_valid < times[-1] - tolerance
            ),
        }
    return result


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

LEVEL_ZH = {"unknown": "未知", "none": "未毁伤", "mild": "轻度", "moderate": "中度", "severe": "重度"}
STATUS_ZH = {
    "normal_completion": "正常完成",
    "long_duration_snapshot_without_normal_stop": "长时快照（无正常结束标记）",
    "running_snapshot": "实时快照（案例仍在运行）",
    "long_snapshot_with_numerical_instability": "长时快照（存在数值不稳定）",
    "invalid_numerical_instability": "无效（数值不稳定）",
    "insufficient_duration_snapshot": "时长不足的快照",
}
CAMPAIGN_ZH = {
    "corrected Q-normalized baseline": "修正入射面归一化基线",
    "probe-corrected sensitivity": "探针修正敏感性方案",
    "adaptive sensitivity; compare separately": "自适应敏感性方案（单独比较）",
    "threshold-search case": "阈值搜索方案",
    "retired legacy-flux provenance": "已停用的旧热流追溯方案",
    "retired numerical diagnostic": "已停用的数值诊断方案",
    "corrected Q-normalized exploratory baseline": "修正入射面归一化探索基线",
    "developmental provenance": "开发过程追溯方案",
}
CONFIG_LABEL_ZH = {
    "purpose": "方案用途", "source_case": "来源案例", "changed_factor": "修改因素",
    "Q_J_cm2": "光冲量 Q（J/cm2）", "yield_kt": "核爆当量（kt）",
    "azimuth_deg": "方位角（度）", "elevation_deg": "俯仰角（度）",
    "target_t_end_s": "目标模拟时长（s）", "mpi_processes": "MPI 进程数",
    "burn_away": "BURN_AWAY", "radiative_fraction": "辐射份额",
    "cfl_max": "最大 CFL", "time_step_dt_s": "指定时间步长（s）",
    "nuclear_ramp_integral_s": "核辐射脉冲积分（s）",
    "plane_peak_irradiance_kw_m2": "入射面峰值辐照度（kW/m2）",
    "max_local_external_flux_kw_m2": "最大局部外部热流（kW/m2）",
    "max_local_fluence_J_cm2": "最大局部积分光冲量（J/cm2）",
    "hrrpua_group_values_kw_m2": "各材料 HRRPUA（kW/m2）",
    "all_hrrpua_values_in_fds_kw_m2": "FDS 中全部 HRRPUA（kW/m2）",
    "audited_group_thickness_m": "审查后的材料厚度（m）",
    "all_layer_thicknesses_in_fds_m": "FDS 中全部材料层厚度（m）",
    "geometry_changed": "几何是否修改", "materials_changed": "材料是否修改",
    "combustion_changed": "燃烧参数是否修改", "external_flux_changed": "外部热流是否修改",
    "ignition_temperature_changed": "点燃温度是否修改", "damage_thresholds_changed": "毁伤阈值是否修改",
    "fds_input": "FDS 输入文件",
}
SYSTEM_LABEL_ZH = {"airframe": "机体结构系统", "avionics": "航空电子系统", "power": "电源系统", "cockpit": "座舱系统"}
EQUIPMENT_LABEL_ZH = {
    "RADM": "雷达罩", "WINS": "有机玻璃舷窗", "BED": "尼龙床垫", "CURT": "尼龙窗帘",
    "U4": "U4 仪器设备", "SEAT": "聚氨酯座椅", "AL2024": "2024 铝合金蒙皮",
    "AL5052": "5052 铝合金风管", "AL7075": "7075 铝合金框架", "O2TANK": "氧气瓶",
    "H1": "导航子系统", "H2": "任务子系统", "H3": "显示子系统", "H4": "通信子系统",
    "H5": "电池", "H6": "电力传输子系统", "H7": "操纵子系统",
}
VALUE_ZH = {
    "unspecified": "未说明", "none recorded": "未记录", "corrected_incident_plane_fluence_normalization": "修正入射面光冲量归一化",
}


def level_zh(level):
    return LEVEL_ZH.get(level, str(level))


def status_zh(status):
    return STATUS_ZH.get(status, str(status))


def campaign_zh(value):
    return CAMPAIGN_ZH.get(value, str(value))


def equipment_label_zh(group, fallback=None):
    return EQUIPMENT_LABEL_ZH.get(group, fallback or group)


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
        parts.append(f'<text x="{x + w / 2:.1f}" y="{subtitle_y:.1f}" text-anchor="middle" class="small" fill="{stroke}">{html.escape(level_zh(level) + (" | " + subtitle if subtitle else ""))}</text>')

    root_w = 360
    root_x = (width - root_w) / 2
    box(root_x, root_y, root_w, box_h, "飞机目标", result["aircraft_level"], "PDF 毁伤树等级")
    parts.append(f'<path class="line" d="M {width / 2:.1f} {root_y + box_h:.1f} V {system_y - 28:.1f}"/>')
    first_center = margin + column_width / 2
    last_center = width - margin - column_width / 2
    parts.append(f'<path class="line" d="M {first_center:.1f} {system_y - 28:.1f} H {last_center:.1f}"/>')

    for index, name in enumerate(columns):
        spec = specs[name]
        x = margin + index * (column_width + gap)
        center = x + column_width / 2
        parts.append(f'<path class="line" d="M {center:.1f} {system_y - 28:.1f} V {system_y:.1f}"/>')
        box(x, system_y, column_width, box_h, SYSTEM_LABEL_ZH.get(name, spec.get("label", name)), result["systems"].get(name, "unknown"), name)
        parts.append(f'<path class="line" d="M {center:.1f} {system_y + box_h:.1f} V {item_y - 16:.1f}"/>')
        items = [(group, "主要节点") for group in spec["major"]] + [(group, "次要节点") for group in spec["secondary"]]
        for row, (group, role) in enumerate(items):
            y = item_y + row * (item_h + item_gap)
            item = result["equipment"].get(group, {"level": "unknown"})
            title = f'{group}  {equipment_label_zh(group, item.get("label", group))}'
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
        parts.append(f'<text x="{lx + 30}" y="{legend_y + 14}" class="small">{level_zh(level)}</text>')
        lx += 128
    parts.append(f'<text x="{width - margin}" y="{legend_y + 14}" text-anchor="end" class="small">严格全重度毁伤：{result["severe_count"]}/{result["total_count"]}</text>')
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
        return "未知：缺少重度毁伤阈值证据"
    threshold = evidence.get("temperature_C", float("nan"))
    required = evidence.get("required_s", float("nan"))
    continuous = evidence.get("continuous_s", 0.0)
    peak = item.get("peak_C", float("nan"))
    if item.get("level") == "severe":
        return f"已达到：峰值 {peak:.1f} C；连续高于 {threshold:g} C 的时间为 {continuous:.1f}/{required:g} s"
    if not math.isfinite(peak):
        return "未知：没有有效的有限温度探针数据"
    if peak < threshold:
        return f"未达到：峰值 {peak:.1f} C < {threshold:g} C"
    return f"未达到：连续高于 {threshold:g} C 的时间仅为 {continuous:.1f}/{required:g} s"


def physical_interpretation(item: dict):
    evidence = item.get("evidence", {}).get("severe", {})
    peak = item.get("peak_C", float("nan"))
    threshold = evidence.get("temperature_C", float("inf"))
    continuous = evidence.get("continuous_s", 0.0)
    required = evidence.get("required_s", float("inf"))
    direct = item.get("positive_external_flux_probe_count", 0)
    if item.get("level") == "unknown":
        return "缺少探针证据，不能形成可靠的物理结论。"
    if item.get("level") == "severe":
        source = "直接外部热流和/或火灾加热" if direct else "舱内二次火灾加热"
        return f"{source}同时提供了足够的温度和持续时间。"
    if peak < threshold:
        if direct:
            return "监测表面接收到正外部热流，但受脉冲能量、材料热惯性和散热影响，峰值仍低于重度毁伤阈值。"
        return "监测表面未分配到正外部热流；几何遮挡后仅靠舱内二次火灾加热，温度低于重度毁伤阈值。"
    if continuous < required:
        return "瞬态光辐射或火灾使温度短暂超过重度阈值，但燃烧或热反馈未维持到规定时间。"
    return "证据组合尚未完全解析，当前不能判为重度毁伤。"


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
            f'该结果是 {result.get("sim_t_s", 0):.1f} s 的长时快照，缺少 FDS 正常结束标记；'
            "在达到 T_END 前，温度和毁伤等级仍可能变化。"
        )
    classification = result.get("campaign_classification", "")
    if "retired" in classification or "provenance" in classification:
        issues.append("这是已停用或仅用于追溯的配置，不纳入当前阈值区间。")
    config = result.get("configuration", {})
    q = config.get("Q_J_cm2")
    local_q = config.get("max_local_fluence_J_cm2")
    if q and local_q is not None and local_q < 0.8 * q:
        issues.append(f"标称 Q={q:g} J/cm2，但最大局部积分光冲量仅为 {local_q:.3g} J/cm2，解释结果时必须考虑归一化和实际受照情况。")
    if config.get("damage_thresholds_changed"):
        issues.append("该案例的毁伤阈值不同于固定标准，因此不能直接用于阈值比较。")
    issues.append("H1-H4 目前以铝合金外壳壁面温度代理内部电子器件温度。")
    return issues


def format_config_value(value):
    if value is None:
        return "未记录"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return VALUE_ZH.get(str(value), str(value))


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
    # queue_runner writes this marker only after the FDS process exits.  Its
    # absence must not be described as an abnormal long snapshot merely
    # because the live DEVC stream has passed 1000 s.
    if not (case_dir / ".fds_exit_code").exists():
        return "running_snapshot"
    if sim_t_s >= 1000:
        return "long_duration_snapshot_without_normal_stop"
    return "insufficient_duration_snapshot"


def propagation_rule_zh(level):
    return {
        "severe": "至少一个主要节点达到重度毁伤",
        "moderate": "主要节点达到中度，或次要节点达到重度毁伤",
        "mild": "至少一个已知节点达到轻度，且未触发更高等级",
        "none": "所有已知节点均未达到毁伤标准",
        "unknown": "证据不足，无法判定",
    }.get(level, "按毁伤树规则传播")


def methodology_markdown(heading_level=2):
    h = "#" * heading_level
    return [
        "", f"{h} 毁伤树评估原则", "",
        f"{h}# 根据 PDF 重新绘制的毁伤树及其逻辑", "",
        "本项目毁伤树的标准来源为用户提供的毁伤标准 PDF。为避免页面截图模糊、跨页和排版干扰，本文不嵌入 PDF 原图，而是依据第 6.2 节、第 6.3 节、表10、表11及表13至表15重新绘制。重绘图保留原标准中的飞机目标、四个系统、功能子系统和毁伤等级传播关系。", "",
        "![PDF 轻度中度重度毁伤树传播逻辑重绘](figures/pdf_three_level_damage_logic.svg)", "",
        "重度毁伤树的底事件关系较为明确，下面进一步展开飞机目标、四个系统及其主要功能节点。", "",
        "![PDF 重度毁伤树详细重绘](figures/pdf_severe_damage_tree_redrawn.svg)", "",
        "PDF 还分别给出了机体结构、航电、电力和座舱系统的下级条件。下图将四个系统的底事件、主要/次要属性和三级触发条件统一重绘。", "",
        "![PDF 四个系统毁伤条件重绘](figures/pdf_system_damage_conditions_redrawn.svg)", "",
        "机体结构系统以机头结构为主要要害节点。机头结构达到重度时系统直接为重度；达到中度且不存在重度时系统为中度；仅达到轻度且不存在更高等级时系统为轻度。当前模型进一步使用 RADM、AL2024 和 AL7075 提供机头、蒙皮和框架的热响应证据。这里的 RADM 明确表示雷达罩物理结构，属于机体或机头结构，不是航电系统中的雷达电子子系统。", "",
        "航电系统的逻辑最需要区分主要和次要节点。PDF 重度毁伤树中，雷达电子子系统和导航子系统是能够直接触发航电系统重度毁伤的主要节点。通信、光电子和电子对抗作为次要节点时，其重度毁伤可在没有主要节点重度的条件下触发系统中度，而不能直接触发系统重度。当前模型将 H1、H2 作为主要航电节点，将 H4 作为次要航电节点；其中 H2 是项目扩展映射。当前模型尚未设置独立的雷达电子子系统监测组，绝不能用 RADM 雷达罩的温度替代雷达电子设备毁伤。", "",
        "电力系统的电池和电力传输子系统均属于主要要害节点。任一节点重度即可使电力系统重度；任一节点中度且不存在重度时，电力系统为中度；只有轻度且不存在更高等级时，电力系统为轻度。当前模型分别使用 H5 和 H6 对应这两个功能节点。", "",
        "座舱系统由环控、窗户及玻璃、座舱内部设施和操纵子系统构成。PDF 图中这些节点均位于直接触发系统等级的主要功能分支。当前模型以 WINS 表征窗户及玻璃，以 BED、CURT、SEAT、U4、H3、AL5052 和 O2TANK 细化座舱内部设施，以 H7 对应操纵子系统。环控子系统目前缺少独立同名设备节点，相关结论不能由其他座舱材料自动替代。", "",
        f"{h}## 逻辑层级", "",
        "毁伤树采用自上而下的事件层级。飞机目标毁伤是顶事件；机体结构、航电、电力和座舱系统毁伤是次顶事件或系统级中间事件；雷达、导航、电池、电力传输、环控、窗户及玻璃、座舱内部设施和操纵子系统等是功能单元或底事件。FDS 并不直接输出“整机毁伤”，而是先提供各材料和设备的温度证据，再由底事件逐层向上推导。", "",
        f"{h}## 飞机目标级逻辑", "",
        "根据 PDF 表11，飞机目标等级由四个系统的最高毁伤等级决定。重度逻辑为：四个系统中至少一个达到重度，即可触发飞机目标重度毁伤。中度逻辑为：至少一个系统达到中度，同时重度系统数量为零。轻度逻辑为：至少一个系统达到轻度，同时中度和重度系统数量均为零。因此该逻辑不是对四个系统求平均，也不要求四个系统全部达到同一等级。", "",
        "可将飞机目标级传播写成优先级关系：`重度 > 中度 > 轻度 > 未毁伤`。程序先检查是否存在重度系统；不存在时再检查中度；仍不存在时再检查轻度。缺少证据的系统保持未知，不能自动当作未毁伤。", "",
        f"{h}## 系统级主要节点与次要节点逻辑", "",
        "根据 PDF 表10，系统重度毁伤的核心条件是至少一个主要要害部位达到重度。系统中度毁伤存在两条路径：第一，至少一个主要要害部位达到中度，且没有主要要害部位达到重度；第二，至少一个次要要害部位达到重度，且没有主要要害部位达到重度。系统轻度毁伤要求至少一个下级节点达到轻度，同时不存在中度或重度触发条件。", "",
        "主要节点和次要节点的区分反映功能重要性。主要节点的重度毁伤可以直接导致系统核心功能完全失效；次要节点通常需要达到更高的物理毁伤程度，才会向上传播为系统中度。当前项目配置中的主要/次要属性必须来自功能结构和 PDF/DMECA 映射，不能为了提高整机等级而随意调整。", "",
        f"{h}## PDF 建树方法", "",
        "PDF 第 6.2 节的建树方法可归纳为四步：第一，以功能为依据，将飞机目标划分为若干系统；第二，把系统毁伤作为次顶事件，把功能单元毁伤作为中间事件，并继续分解到子系统或要害部位底事件；第三，依据不同毁伤等级的 DMECA 影响确定主要和次要要害部位，再用逻辑门连接；第四，在建树前全面核对飞机结构组成、设备位置和功能依赖关系。", "",
        "从物理意义上看，底事件回答“某个材料或设备是否因受热达到规定毁伤状态”，系统事件回答“这些底事件是否足以使系统核心功能降级或失效”，顶事件回答“系统失效是否使地面停放飞机的整体功能达到相应毁伤等级”。这三个问题必须分层回答，不能用某个局部最高温度直接替代整机毁伤结论。", "",
        "当前新版模型在 PDF 原始树基础上增加了材料实体和 H1-H7 设备节点。二者的关系如下，属于项目映射而不是对 PDF 原图的逐字替换：", "",
        "| PDF 原始系统或节点 | 当前监测模型中的映射 | 说明 |", "|---|---|---|",
        "| 机体结构、机头结构 | RADM、AL2024、AL7075 | RADM 是雷达罩结构；用雷达罩、蒙皮和框架表面热响应表征机体结构受热毁伤 |",
        "| 航电子系统 | H1、H2、H4 | H1 导航和 H4 通信具有功能对应；H2 属于项目扩展；当前没有独立雷达电子子系统节点，RADM 不能代替它 |",
        "| 电池、电力传输子系统 | H5、H6 | 与 PDF 电力系统底事件直接对应 |",
        "| 窗户及玻璃 | WINS | 与 PDF 座舱系统底事件直接对应 |",
        "| 座舱内部设施 | BED、CURT、SEAT、U4、H3、AL5052、O2TANK | 按新版几何中的床垫、窗帘、座椅、仪器和内部设备细化 |",
        "| 操纵子系统 | H7 | 与 PDF 座舱系统操纵子系统对应 |", "",
        f"{h}# 1. 评估对象与证据链", "",
        "本项目采用“FDS 热响应输出、设备级温度与持续时间判据、系统级毁伤树传播、整机级结果”四级证据链。FDS 首先计算外部光辐射、材料受热、热解、点燃、火焰传播和舱内二次加热；随后从各材料或设备表面的壁面温度探针中提取温度历程。每个设备布置多个冗余探针，评估时在每个时刻选取所有几何有效探针的最高温度，形成动态包络。该处理用于捕捉设备不同受照面或燃烧过程中热点位置的变化，避免只用单个固定探针漏掉局部最高温度。", "",
        "![毁伤评估证据链](figures/damage_assessment_evidence_chain.svg)", "",
        "探针只有在几何位置有效且能够输出有限温度值时才参与评估。若某个表面烧蚀、被遮挡或个别探针失效，动态包络可以自动由其余有效探针继续提供证据。需要强调的是，动态包络表示被监测表面范围内的最高温度，并不等于整个实体内部每一点的真实最高温度；尤其 H1-H4 当前使用铝合金外壳壁面温度代理内部电子元件温度，因此其结论仍包含等效建模假设。", "",
        f"{h}# 2. 设备级温度与持续时间判据", "",
        "每个设备均设置轻度、中度和重度三档温度与持续时间组合判据。只有温度达到规定阈值，并且连续保持时间不短于规定时长，才认为该档毁伤成立。程序计算的是最长连续超阈时间，而不是把多个彼此分离的短时高温片段简单累加。这样可以避免瞬态光辐射峰值或短时火焰扫过被误判为持续性热毁伤。", "",
        "![温度与最长连续持续时间联合判据](figures/temperature_duration_criterion.svg)", "",
        "设备最终等级取其满足的最高等级。例如，一个设备可以满足轻度和中度判据，但若重度温度只短暂超过而持续时间不足，则最终仍为中度。若峰值温度从未达到重度阈值，报告将其归为“峰值温度受限”；若峰值达到阈值但保持时间不足，则归为“持续时间受限”。证据缺失时保留“未知”，不能按未毁伤处理。", "",
        f"{h}# 3. 外部热流与火灾加热的解释原则", "",
        "正外部热流探针数量用于判断设备是否存在直接受照表面。存在正外部热流并不保证设备达到毁伤，因为入射角、遮挡、材料吸收率、厚度、导热、热容、热解和散热共同决定最终温升。没有正外部热流探针的设备主要依赖舱内火灾、烟气辐射和邻近可燃物燃烧产生的二次加热，其温升通常更慢，并高度依赖火灾是否能够持续。", "",
        "对于峰值很高但超阈时间很短的设备，物理上通常意味着核辐射脉冲或局部火焰产生了瞬态加热，但材料热解、燃烧反馈或邻近火源不足以维持温度。对于峰值始终偏低的设备，则需要区分直接受照强度不足、几何遮挡、材料热惯性过大、表层厚度设置、燃烧参数以及探针位置等原因，不能仅通过降低毁伤阈值来获得目标结果。", "",
        f"{h}# 4. 设备到系统的毁伤树传播", "",
        "设备节点按照主要节点和次要节点归入机体结构、航空电子、电源和座舱四个系统。系统级传播遵循以下原则：至少一个主要节点达到重度时，系统判为重度；主要节点达到中度，或次要节点达到重度且没有主要节点达到重度时，系统判为中度；至少一个已知节点达到轻度且没有更高等级时，系统判为轻度；全部已知节点均未达到毁伤条件时，系统判为未毁伤。", "",
        "整机等级取四个系统已知等级中的最高等级。因此，只要一个关键系统传播为重度，PDF 毁伤树意义下的整机目标就可以判为重度。这一原则体现关键系统失效可能导致整机任务能力丧失，并不要求所有设备同时达到重度。", "",
        f"{h}# 5. PDF 整机等级与严格全毁伤目标", "",
        "本研究同时报告两种不能混用的结果。第一种是依据 PDF 毁伤树传播得到的整机等级；第二种是严格全设备重度毁伤指标，即 17 个设备组全部达到重度。一个案例可能因座舱或机体结构中的关键主要节点重度毁伤而得到“整机重度”，但严格结果仍只有 4/17 或 7/17。光冲量阈值搜索的目标是后者，因此必须以 17/17 作为成功条件，同时保留 PDF 整机等级用于工程任务能力解释。", "",
        f"{h}# 6. 正常完成与长时快照", "",
        "包含 `STOP: FDS completed successfully`、达到目标时长且不存在数值不稳定的案例属于正常完成结果。模拟时间达到 1000 s 但缺少正常结束标记的案例可以作为长时快照用于阶段分析，因为核辐射脉冲和主要火灾发展通常已经历较长时间；但其结果仍是临时证据，后续温度和持续时间可能变化。低于 1000 s 的快照不进入正式汇总，发生数值不稳定的结果必须单独标记，不能直接用于阈值结论。", "",
        f"{h}# 7. 阈值搜索与可比性", "",
        "比较不同光冲量案例时，必须保持核爆当量、入射角、几何、材料、厚度、燃烧参数、BURN_AWAY、探针和毁伤标准一致，只改变入射面归一化光冲量 Q。只有同一参数族中的案例才能建立失败与成功区间并进行二分搜索。修改厚度、HRRPUA、角度或材料参数的敏感性案例必须单独分类，不能与基线案例混合得出单一阈值。", "",
    ]


def detailed_result_explanation(result: dict):
    equipment = result["equipment"]
    severe = [group for group, item in equipment.items() if item.get("level") == "severe"]
    peak_limited, duration_limited, shielded = [], [], []
    for group, item in equipment.items():
        if item.get("level") == "severe":
            continue
        ev = item.get("evidence", {}).get("severe", {})
        peak = item.get("peak_C", float("nan"))
        threshold = ev.get("temperature_C", float("inf"))
        if item.get("positive_external_flux_probe_count", 0) == 0:
            shielded.append(group)
        if math.isfinite(peak) and peak < threshold:
            peak_limited.append(group)
        elif ev.get("continuous_s", 0) < ev.get("required_s", float("inf")):
            duration_limited.append(group)

    lines = ["", "## 按毁伤树原则对本案例的详细解释", ""]
    status = result.get("evaluation_status", "unknown")
    if status == "normal_completion":
        lines.append("该案例已正常运行到目标时长，且日志中存在 FDS 正常完成标记，因此可作为正式结果参与同参数族的阈值比较。")
    else:
        lines.append(f"该案例当前属于{status_zh(status)}，有效模拟时间为 {result.get('sim_t_s', 0):.1f} s。它可以反映已经形成的温度峰值和累计持续时间，但不能替代正常完成结果；所有临界设备仍需在完整结果中复核。")

    config = result.get("configuration", {})
    q = config.get("Q_J_cm2")
    local_q = config.get("max_local_fluence_J_cm2")
    if q and local_q is not None:
        lines.append(f"该案例标称入射面光冲量为 {q:g} J/cm2，模型表面的最大局部积分光冲量为 {local_q:.3f} J/cm2，约为标称值的 {100 * local_q / q:.1f}%。因此设备实际受照还受到入射角、表面朝向与几何遮挡影响，不能把标称 Q 直接等同于每个设备表面接收的光冲量。")

    if severe:
        lines.append(f"按照设备级温度与持续时间判据，当前达到重度毁伤的设备组共有 {len(severe)} 个：{', '.join(severe)}。这些设备不仅达到重度温度阈值，而且最长连续超阈时间也满足规定时长，因此其重度结论具有完整的温度和时间证据。")
    else:
        lines.append("当前没有设备同时满足重度温度阈值与持续时间要求，因此严格重度毁伤数为 0。")

    if peak_limited:
        details = []
        for group in peak_limited:
            item = equipment[group]
            ev = item["evidence"]["severe"]
            details.append(f"{group}（峰值 {item['peak_C']:.1f} C，阈值 {ev['temperature_C']:g} C）")
        lines.append("峰值温度受限设备包括：" + "、".join(details) + "。这些对象尚未进入重度判据温度区间，继续延长模拟时间并不会自动补足峰值条件；需要结合直接受照、遮挡和二次火灾强度判断其原因。")

    if duration_limited:
        details = []
        for group in duration_limited:
            item = equipment[group]
            ev = item["evidence"]["severe"]
            details.append(f"{group}（{ev['continuous_s']:.1f}/{ev['required_s']:g} s，高于 {ev['temperature_C']:g} C）")
        lines.append("持续时间受限设备包括：" + "、".join(details) + "。这些对象已经出现足够高的瞬态峰值，但热解、燃烧或邻近火灾反馈没有把温度维持到标准要求，因此不能仅凭最高温度判为重度毁伤。")

    if shielded:
        lines.append(f"{', '.join(shielded)} 的有效监测面没有记录到正外部热流，它们主要依靠舱内二次火灾加热。若这些设备未达到重度，优先应检查 DDA 可见性、设备实际朝向、邻近可燃物燃烧持续性及探针是否覆盖热点，而不是直接降低材料强度或毁伤标准。")

    system_parts = []
    for name, detail in result["system_evidence"].items():
        triggers = "、".join(detail.get("triggers", [])) or "无明确触发节点"
        system_parts.append(f"{SYSTEM_LABEL_ZH.get(name, name)}为{level_zh(detail['level'])}，触发节点为{triggers}")
    lines.append("系统级传播结果为：" + "；".join(system_parts) + "。系统等级由主要节点和次要节点按既定规则传播，不是按系统内所有设备温度求平均。")
    lines.append(f"最终 PDF 毁伤树整机等级为{level_zh(result['aircraft_level'])}，而严格全设备结果为 {result['severe_count']}/{result['total_count']}。前者说明至少一个关键系统已达到相应任务毁伤等级；后者说明距离“所有材料和设备均重度毁伤”的研究目标仍有 {result['total_count'] - result['severe_count']} 个设备组未满足。两者必须同时保留，不能用整机重度替代 17/17。")
    lines.append("因此，本案例是否能够作为全毁伤阈值的成功点，只取决于严格结果是否达到 17/17，并且案例是否正常完成。未达到 17/17 时，应根据上面的峰值受限、持续时间受限和遮挡分类确定下一步物理参数研究方向。")
    return lines


def case_markdown(result: dict, image_ref: str):
    lines = [
        f'# 完整毁伤树评估：{result["case"]}', "",
        f'- 模拟时间：**{result["sim_t_s"]:.2f} s**',
        f'- 来源目录：`{result.get("case_directory", "未知")}`',
        f'- 方案分类：**{campaign_zh(result.get("campaign_classification", "未分类"))}**',
        f'- 评估状态：**{status_zh(result.get("evaluation_status", "unknown"))}**',
        f'- PDF 毁伤树整机等级：**{level_zh(result["aircraft_level"])}**',
        f'- 严格全设备重度毁伤结果：**{result["severe_count"]}/{result["total_count"]}** '
        f'（全部重度毁伤={"是" if result["all_severe"] else "否"}）',
        '- 最高温度定义：几何位置有效的冗余壁面温度探针动态包络最大值。',
        '- 注意：严格的 17/17 指标不等同于 PDF 毁伤树的整机等级判据。', "",
        '## 案例配置', "",
        '| 参数 | 数值 |', '|---|---|',
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
        lines.append(f'| {CONFIG_LABEL_ZH.get(key, key)} | {value} |')
    lines += ["", "## 已知问题与结果有效性", ""]
    for issue in result_issues(result):
        lines.append(f'- {issue}')
    lines += ["", '## 毁伤树', "", f'![毁伤树]({image_ref})', "",
        '## 系统级传播结果', "",
        '| 系统 | 等级 | 触发节点 | 采用的传播规则 |',
        '|---|---:|---|---|',
    ]
    for name, detail in result["system_evidence"].items():
        label = SYSTEM_LABEL_ZH.get(name, TREE["systems"][name].get("label", name))
        triggers = ", ".join(detail["triggers"]) or "无"
        lines.append(f'| {label}（`{name}`） | {level_zh(detail["level"])} | {triggers} | {propagation_rule_zh(detail["level"])} |')
    lines += ["", "## 完整设备毁伤评估", "",
              '| 设备组 | 设备名称 | 毁伤树角色 | 等级 | 峰值温度（C） | 轻度证据 | 中度证据 | 重度证据 | 重度毁伤结论 | 物理解释 | 正外部热流探针数 | 有效温度探针数 |',
              '|---|---|---|---:|---:|---|---|---|---|---|---:|---:|']
    roles = {}
    for system, spec in TREE["systems"].items():
        for group in spec["major"]:
            roles[group] = f'{SYSTEM_LABEL_ZH.get(system, system)}：主要节点'
        for group in spec["secondary"]:
            roles[group] = f'{SYSTEM_LABEL_ZH.get(system, system)}：次要节点'
    for group, item in result["equipment"].items():
        lines.append(
            f'| {group} | {equipment_label_zh(group, item.get("label", group))} | {roles.get(group, "未映射")} | '
            f'{level_zh(item.get("level", "unknown"))} | {item.get("peak_C", float("nan")):.1f} | '
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
    lines += ["", "## 评估结论与解释", "",
              f'- 未达到重度或证据未知的设备组：**{", ".join(not_severe) if not_severe else "无"}**。',
              f'- 重度毁伤未满足的原因统计：**{peak_shortfall} 项受峰值温度限制**，**{duration_shortfall} 项受持续时间限制**。',
              f'- 整机等级取各系统已知等级中的最高等级：**{level_zh(result["aircraft_level"])}**。',
              '- H2（任务子系统）和 H3（显示子系统）属于当前模型的专用映射，其通用电子设备阈值并非 PDF 中的同名条目。',
              '- H1-H4 探针当前测量铝合金外壳表面温度，并将其作为内部电子器件温度的代理。', ""]
    lines += detailed_result_explanation(result)
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
    lines = ["# 长时及正常完成案例毁伤树评估汇总", "",
             "本报告在每次评估后自动重建，包含 FDS 正常完成案例，以及明确标注的模拟时间不小于 1000 s 的长时快照。", "",
             "| 案例 | 状态 | 方案分类 | Q（J/cm2） | 模拟时间（s） | PDF 整机等级 | 严格重度毁伤数 |",
             "|---|---|---|---:|---:|---:|---:|"]
    lines = lines[:4] + methodology_markdown(2) + ["", "## 案例结果汇总", ""] + lines[4:]
    for item in results:
        lines.append(f'| {item["case"]} | {status_zh(item.get("evaluation_status", "unknown"))} | '
                     f'{campaign_zh(item.get("campaign_classification", "未分类"))} | '
                     f'{item.get("Q_J_cm2", float("nan")):g} | '
                     f'{item.get("sim_t_s", 0):.1f} | {level_zh(item.get("aircraft_level", "unknown"))} | '
                     f'{item.get("severe_count", 0)}/{item.get("total_count", 0)} |')
    for item in results:
        assessment_path = item.pop("_assessment_path")
        case_rel = assessment_path.parent.relative_to(ROOT).as_posix()
        lines += ["", "---", "", case_markdown(item, f'../{case_rel}/damage_tree.svg').replace("# 完整", "## 完整", 1)]
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
        validity = probe_validity(times, columns, names)
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
                            "probe_validity": validity,
                            "probe_trailing_dropout_count": sum(
                                item["trailing_dropout"] for item in validity.values()
                            ),
                            "missing_temperature_policy": (
                                "missing values are excluded, never filled with zero; "
                                "finite history and pre-dropout peak are retained"
                            ),
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
              "burnaway_assessment_policy": {
                  "enabled": bool(summary.get("burn_away", False)),
                  "surface_probe_dropout_is_supporting_evidence_only": True,
                  "strict_temperature_duration_criteria_unchanged": True,
                  "gas_temperature_does_not_replace_wall_temperature": True,
              },
              "systems": systems, "system_evidence": details, "aircraft_level": aircraft,
              "evaluation_status": evaluation_status(case_dir, sim_t_s),
              "configuration": case_configuration(case_dir, summary),
              "assessment_standard": TREE["interpretation"]["source"],
              "damage_criteria_version": CRITERIA_DOC.get("schema_version", "unknown"),
              "damage_criteria_source": CRITERIA_DOC.get("source", "unknown"),
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

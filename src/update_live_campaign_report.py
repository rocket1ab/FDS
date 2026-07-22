#!/usr/bin/env python3
"""Build the Chinese live-monitor report for the active HRRPUA campaign."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FAMILY = "adapt_HRRupper_thickness_audit"
LEVEL_ZH = {
    "unknown": "未知", "none": "未毁伤", "mild": "轻度",
    "moderate": "中度", "severe": "重度",
}
NODES = {
    "node01": [50],
    "node04": [400, 300],
    "node05": [200, 100],
}


def case_name(q: int) -> str:
    return f"Q{q:04d}_W0100_az270_el15_H1H7_v5_Qnorm_{FAMILY}"


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def status_label(result: dict, queue_state: str) -> str:
    status = result.get("evaluation_status")
    if status == "normal_completion":
        return "正常完成"
    if status in {"long_duration_snapshot_without_normal_stop", "long_snapshot_with_numerical_instability"}:
        return "长时快照"
    if queue_state in {"running", "running_unreachable"}:
        return "实时快照（运行中）"
    return "实时快照（未完成）"


def fmt(value, digits: int = 1) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "--"


def main() -> None:
    checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
    statuses = {node: load_json(ROOT / "queue" / f"{node}_status.json") for node in NODES}
    results = {}
    for queue in NODES.values():
        for q in queue:
            path = ROOT / "cases_adaptive" / case_name(q) / "damage_assessment.json"
            if path.exists():
                results[q] = load_json(path)

    lines = [
        "# H1-H7 高 HRRPUA 与审查厚度方案实时毁伤监测", "",
        f"- 本次检查时间：**{checked_at}**",
        "- 固定参数：W=100 kt，az=270 deg，el=15 deg，T_END=1500 s，入射面光冲量归一化。",
        "- 本页只汇总 `_adapt_HRRupper_thickness_audit` 参数族，不与旧热流、旧厚度或其它敏感性方案混用。",
        "- 运行中结果属于实时快照，后续温度和持续时间仍会变化；只有 FDS 正常运行到 1500 s 才是最终结果。", "",
        "## 节点与总体状态", "",
        "| 节点 | 当前/队列案例 | 状态 | 数据时间（s） | 严格重度毁伤 | PDF整机等级 |",
        "|---|---|---|---:|---:|---|",
    ]
    for node, queue in NODES.items():
        status = statuses[node]
        current = status.get("case", case_name(queue[0]))
        q = next((value for value in queue if f"Q{value:04d}_" in current), queue[0])
        result = results.get(q, {})
        queue_text = " -> ".join(f"Q{value}" for value in queue)
        lines.append(
            f"| {node} | {queue_text} | {status_label(result, status.get('state', ''))} | "
            f"{fmt(result.get('sim_t_s', status.get('simulation_time_s')))} / 1500 | "
            f"{result.get('severe_count', '--')}/{result.get('total_count', 17)} | "
            f"{LEVEL_ZH.get(result.get('aircraft_level'), '--')} |"
        )

    lines += [
        "", "## 最新曲线", "",
        "温度曲线取同一对象全部几何有效探针在每个时刻的最大值，形成动态包络。它是监测点集合中的最大值，不等同于连续表面场的绝对最大值。", "",
        "![各材料与设备最大温度包络](../outputs/live_HRRupper_thickness_monitor/material_temperature_envelopes.png)", "",
        "![全域热释放速率](../outputs/live_HRRupper_thickness_monitor/whole_domain_hrr.png)", "",
        "![材料HRRPUA输入上限](../outputs/live_HRRupper_thickness_monitor/nominal_material_hrrpua_inputs.png)", "",
        "HRR 曲线是 FDS 全域时变输出；当前模型没有逐材料时变 HRRPUA 输出，因此第三幅图列示各 SURF 的 HRRPUA 输入上限，不能将其解释为材料在每个时刻实际释放的热量。", "",
        "## 逐案例毁伤状态", "",
    ]

    for q in sorted(results):
        result = results[q]
        equipment = result.get("equipment", {})
        lines += [
            f"### Q={q} J/cm2", "",
            f"状态：**{status_label(result, next((s.get('state', '') for s in statuses.values() if f'Q{q:04d}_' in s.get('case', '')), ''))}**；"
            f"数据截止 **{fmt(result.get('sim_t_s'))} s**；严格重度毁伤 **{result.get('severe_count', 0)}/{result.get('total_count', 17)}**；"
            f"PDF毁伤树整机等级 **{LEVEL_ZH.get(result.get('aircraft_level'), '未知')}**。", "",
            "| 材料/设备 | 毁伤等级 | 最高温度（C） | 重度阈值连续时间（s） | 重度要求（s） | 判定 |",
            "|---|---|---:|---:|---:|---|",
        ]
        for group, item in equipment.items():
            severe = item.get("evidence", {}).get("severe", {})
            level = item.get("level", "unknown")
            reason = "达到重度" if level == "severe" else (
                "峰值或持续时间不足" if level != "unknown" else "探针证据不足"
            )
            lines.append(
                f"| {group} | {LEVEL_ZH.get(level, level)} | {fmt(item.get('peak_C'))} | "
                f"{fmt(severe.get('continuous_s'))} | {fmt(severe.get('required_s'))} | {reason} |"
            )
        systems = result.get("systems", {})
        lines += [
            "", "系统毁伤：" + "；".join(
                f"{name}={LEVEL_ZH.get(level, level)}" for name, level in systems.items()
            ) + "。", "",
            f"![Q={q}毁伤树](../cases_adaptive/{case_name(q)}/damage_tree.svg)", "",
        ]

    lines += [
        "## 当前判断", "",
        "PDF整机等级按关键系统毁伤向上传播，因此可能在少数关键节点达到重度后即判为整机重度；严格阈值搜索则要求17个材料/设备组全部重度。两项指标必须并列报告，不能相互替代。",
        "RADM代表雷达罩物理结构。其热毁伤可通过透波性能或结构变形影响雷达功能，但不能直接视为雷达电子子系统温度证据。", "",
    ]
    report = ROOT / "reports" / "live_HRRupper_thickness_damage_monitor.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build the Chinese live-monitor report for the active HRRPUA campaign."""
from __future__ import annotations

import json
import re
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
AMBIENT_C = 20.0
THERMAL = {
    "RADM": ("E玻璃纤维复合材料", 2540.0, 1000.0, 0.100),
    "WINS": ("PMMA", 1190.0, 1460.0, 0.025),
    "BED": ("尼龙床垫表层", 1140.0, 1700.0, 0.00089),
    "CURT": ("尼龙窗帘", 1140.0, 1700.0, 0.003),
    "U4": ("环氧玻璃纤维", 2540.0, 1000.0, 0.006),
    "SEAT": ("聚氨酯泡沫", 35.0, 1400.0, 0.150),
    "AL2024": ("铝合金2024", 2780.0, 875.0, 0.002),
    "AL5052": ("铝合金5052", 2680.0, 880.0, 0.0015),
    "AL7075": ("铝合金7075", 2810.0, 960.0, 0.003),
    "O2TANK": ("铝合金7075氧气瓶壁", 2810.0, 960.0, 0.005),
    "H1": ("铝合金6061外壳", 2700.0, 896.0, 0.003),
    "H2": ("铝合金6061外壳", 2700.0, 896.0, 0.003),
    "H3": ("铝合金6061外壳", 2700.0, 896.0, 0.003),
    "H4": ("铝合金6061外壳", 2700.0, 896.0, 0.003),
    "H5": ("铝合金6061外壳", 2700.0, 896.0, 0.003),
    "H6": ("PVC塑料", 1449.0, 840.0, 0.001),
    "H7": ("CR橡胶", 1500.0, 1120.0, 0.002),
}
COMBUSTION = {
    "RADM": (400.0, 840.0), "WINS": (250.0, 806.0),
    "BED": (250.0, 790.0), "CURT": (250.0, 324.0),
    "U4": (350.0, 840.0), "SEAT": (250.0, 860.0),
    "H6": (468.6, 259.0), "H7": (410.0, 458.0),
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


def group_external_flux(case_dir: Path, group: str) -> float:
    fds = next(case_dir.glob("*.fds"), None)
    if not fds:
        return 0.0
    text = fds.read_text(encoding="utf-8", errors="replace")
    values = []
    for block in re.findall(r"&SURF\b.*?/", text, flags=re.I | re.S):
        if not re.search(rf"\bID\s*=\s*'{re.escape(group)}_R\d+'", block, flags=re.I):
            continue
        match = re.search(r"\bEXTERNAL_FLUX\s*=\s*([-+0-9.Ee]+)", block, flags=re.I)
        if match:
            values.append(float(match.group(1)))
    return max(values, default=0.0)


def valid_flux_coverage(case_dir: Path, group: str, item: dict) -> tuple[int, int, float]:
    registry = load_json(case_dir / "monitor_registry.json").get(group, [])
    excluded = set(item.get("excluded_invalid_probes", []))
    valid = [probe for probe in registry if probe.get("wt") not in excluded]
    positive = [probe for probe in valid if float(probe.get("base_flux", 0) or 0) > 0]
    maximum = group_external_flux(case_dir, group)
    return len(positive), len(valid), maximum


def failure_analysis(q: int, case_dir: Path, group: str, item: dict) -> list[str]:
    severe = item.get("evidence", {}).get("severe", {})
    threshold = float(severe.get("temperature_C", 0) or 0)
    required = float(severe.get("required_s", 0) or 0)
    continuous = float(severe.get("continuous_s", 0) or 0)
    peak = float(item.get("peak_C", 0) or 0)
    material, density, cp, thickness = THERMAL[group]
    areal_capacity = density * cp * thickness
    ideal_energy_j_cm2 = areal_capacity * max(threshold - AMBIENT_C, 0) / 1.0e4
    positive, valid, max_flux = valid_flux_coverage(case_dir, group, item)
    lines = [
        f"##### {group}：{material}", "",
        f"当前峰值为 **{peak:.1f} C**，重度判据为 **{threshold:g} C 持续 {required:g} s**，"
        f"实际最长连续时间为 **{continuous:.1f} s**。",
        "",
        f"单位面积热容量为 `rho*cp*d = {density:g}*{cp:g}*{thickness:g} = "
        f"{areal_capacity:.0f} J/(m2*K)`；从 {AMBIENT_C:g} C 升至重度阈值所需的理想显热约为 "
        f"`{ideal_energy_j_cm2:.1f} J/cm2`。该值忽略反射、角度投影、向实体内部导热、对流、"
        "辐射散热和热解，只用于解释热惯性，不能直接当作光冲量阈值。",
        "",
        f"有效温度探针中有 **{positive}/{valid}** 个对应正外部热流面，登记峰值为 "
        f"**{max_flux:g} kW/m2**。标称 Q={q} J/cm2 是入射平面光冲量，不等于该对象实际吸收的光冲量。",
        "",
    ]
    if peak < threshold:
        gap = threshold - peak
        if positive == 0:
            mechanism = (
                f"峰值仍低于重度阈值 **{gap:.1f} C**，且有效探针没有直接受照面。"
                "其升温主要来自邻近火焰、热烟气和舱内辐射，因此结果受二次火灾位置与持续性控制。"
            )
        elif positive < valid:
            mechanism = (
                f"峰值仍低于重度阈值 **{gap:.1f} C**。对象只有部分监测面直接受照，"
                "未受照部分及内部导热共同削弱局部脉冲升温，脉冲后散热又使温度回落。"
            )
        else:
            mechanism = (
                f"峰值仍低于重度阈值 **{gap:.1f} C**。虽然监测面直接受照，但实际吸收能量"
                "受投影、表面换热和材料热惯性限制，且后续二次火灾没有提供足够持续加热。"
            )
    else:
        mechanism = (
            f"峰值已经超过重度温度阈值，但还缺少 **{max(required-continuous, 0):.1f} s** 连续保持时间。"
            "这属于持续时间不足，而不是峰值温度不足；后续若温度重新升高并连续越过阈值，等级仍可能改变。"
        )
    lines += [mechanism, ""]
    if group in COMBUSTION:
        ignition, hrrpua = COMBUSTION[group]
        if peak < ignition:
            lines += [
                f"该表面设置 `IGNITION_TEMPERATURE={ignition:g} C`、`HRRPUA={hrrpua:g} kW/m2`。"
                f"当前峰值低于点燃温度 **{ignition-peak:.1f} C**，因此尚不能依靠自身燃烧维持升温；"
                "提高HRRPUA本身在未点燃前不会生效。", "",
            ]
        else:
            lines += [
                f"该表面设置 `IGNITION_TEMPERATURE={ignition:g} C`、`HRRPUA={hrrpua:g} kW/m2`，"
                "峰值已越过点燃温度。若仍未满足重度判据，重点应检查点燃后的有效燃烧面积、"
                "持续热释放、邻近表面的热反馈以及探针是否覆盖持续热点。", "",
            ]
    elif group in {"H1", "H2", "H3", "H4", "H5"}:
        lines += [
            "该对象当前只建模为不可燃的3 mm铝合金6061外壳，没有内部电路板、线缆或聚合物部件，"
            "也没有自身HRRPUA。因此外部脉冲结束后只能依靠邻近火灾继续加热。当前判定反映的是"
            "铝壳表面热毁伤代理，不等同于真实内部电子器件一定未发生功能失效。", "",
        ]
    return lines


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
        not_severe = [(group, item) for group, item in equipment.items()
                      if item.get("level") != "severe"]
        if not_severe:
            lines += ["#### 未达到重度毁伤对象的逐项机理分析", "",
                      "下列计算均为当前实时快照。对于峰值不足和持续时间不足分别给出原因，不把二者混用。", ""]
            case_dir = ROOT / "cases_adaptive" / case_name(q)
            for group, item in not_severe:
                lines += failure_analysis(q, case_dir, group, item)

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

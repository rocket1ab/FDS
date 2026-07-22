#!/usr/bin/env python3
"""Incrementally append verification results to the grid/yield Markdown report."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "cases_verification" / "verification_manifest.json"
REPORT = ROOT / "reports" / "grid_and_yield_independence_verification.md"


def load(path: Path) -> Optional[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def baseline(q: int) -> Optional[dict]:
    name = f"Q{q:04d}_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRupper_thickness_audit"
    return load(ROOT / "cases_adaptive" / name / "damage_assessment.json")


def result_row(case: str, root: Path, base: Optional[dict] = None) -> str:
    result = load(root / case / "damage_assessment.json")
    if not result:
        return f"| `{case}` | 待运行 | - | - | - |"
    peaks = [item.get("peak_C") for item in result.get("equipment", {}).values() if item.get("peak_C") is not None]
    peak = max(peaks, default=float("nan"))
    delta = "-"
    if base:
        base_peaks = [item.get("peak_C") for item in base.get("equipment", {}).values() if item.get("peak_C") is not None]
        base_peak = max(base_peaks, default=0.0)
        delta = f"{(peak-base_peak)/base_peak*100:+.1f}%" if base_peak else "-"
    return (f"| `{case}` | {result.get('evaluation_status')} | "
            f"{result.get('sim_t_s', 0):.1f} | {result.get('severe_count')}/{result.get('total_count')} | "
            f"{peak:.1f}（{delta}） |")


def main() -> None:
    manifest = load(MANIFEST)
    lines = ["# 网格分辨率与核爆当量独立性验证", "",
             "更新时间由各案例评估完成时自动写入。所有结果采用同一毁伤判据。", "",
             "## 网格分辨率对照", "",
             "粗网格仅修改 MESH 的 IJK，单元总数约为现网格的1/8；其余物理输入不变。", "",
             "| 案例 | 状态 | 模拟时间（s） | 重度毁伤 | 全组最高温度°C（相对现网格） |",
             "|---|---|---:|---:|---:|"]
    for case in manifest["grid_cases_in_order"]:
        q = int(case[1:5])
        lines.append(result_row(case, ROOT / "cases_verification" / "grid_coarse", baseline(q)))
    lines += ["", "## 固定 Q=50 J/cm² 的当量对照", "",
              "仅改变核脉冲时间尺度及其倒数峰值缩放，积分光冲量保持不变。", "",
              "| 案例 | 状态 | 模拟时间（s） | 重度毁伤 | 全组最高温度°C |",
              "|---|---|---:|---:|---:|"]
    for case in manifest["yield_cases_in_order"]:
        lines.append(result_row(case, ROOT / "cases_verification" / "yield_Q50"))
    lines += ["", "## 判定原则", "",
              "网格一致性不能只看整机毁伤等级，还必须比较逐设备峰值温度、阈值持续时间、HRR峰值与积分及点火顺序。建议关键连续量相对差不超过10%，且17组毁伤等级和毁伤树结论不改变。", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(REPORT)


if __name__ == "__main__":
    main()

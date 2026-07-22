#!/usr/bin/env python3
"""Plot the active HRRPUA-upper campaign's live thermal snapshots."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CRITERIA = json.loads(
    (ROOT / "config" / "damage_criteria.json").read_text(encoding="utf-8")
)["groups"]
GROUPS = list(CRITERIA)
COLORS = ["#00796b", "#c85a17", "#31557c"]
GROUP_LABELS = {
    "RADM": "雷达罩", "WINS": "舷窗", "BED": "床垫", "CURT": "窗帘",
    "U4": "U4设备", "SEAT": "座椅", "AL2024": "2024铝合金蒙皮",
    "AL5052": "5052铝合金风道", "AL7075": "7075铝合金框架",
    "O2TANK": "氧气瓶", "H1": "导航子系统", "H2": "任务子系统",
    "H3": "显示子系统", "H4": "通信子系统", "H5": "电池",
    "H6": "电力传输子系统", "H7": "操纵子系统",
}

# These are input maxima from the current SURF definitions, not measured outputs.
NOMINAL_HRRPUA = {
    "RADM": 840.0,
    "WINS": 806.0,
    "BED": 790.0,
    "CURT": 324.0,
    "U4": 840.0,
    "SEAT": 860.0,
    "H6": 259.0,
    "H7": 458.0,
}


def setup_plot_style() -> None:
    plt.rcParams.update({
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"],
        "axes.unicode_minus": False,
    })


def read_fds_csv(path: Path) -> dict[str, np.ndarray]:
    rows = list(csv.reader(path.open(encoding="utf-8-sig", errors="replace")))
    header_index = next(
        i for i, row in enumerate(rows)
        if row and row[0].strip().strip('"').lower() == "time"
    )
    header = [item.strip().strip('"') for item in rows[header_index]]
    values = []
    for row in rows[header_index + 1 :]:
        if len(row) < len(header):
            continue
        try:
            values.append([float(value) for value in row[: len(header)]])
        except ValueError:
            continue
    data = np.asarray(values, dtype=float)
    if data.size == 0:
        return {name: np.asarray([], dtype=float) for name in header}
    return {name: data[:, index] for index, name in enumerate(header)}


def envelope(columns: dict[str, np.ndarray], names: list[str]) -> np.ndarray | None:
    usable = [columns[name] for name in names if name in columns]
    return np.nanmax(np.vstack(usable), axis=0) if usable else None


def load_case(case_dir: Path) -> dict:
    registry = json.loads((case_dir / "monitor_registry.json").read_text(encoding="utf-8"))
    devc = read_fds_csv(next(case_dir.glob("*_devc.csv")))
    hrr = read_fds_csv(next(case_dir.glob("*_hrr.csv")))
    temperatures = {}
    heat_fluxes = {}
    for group in GROUPS:
        probes = registry.get(group, [])
        temperatures[group] = envelope(devc, [probe["wt"] for probe in probes])
        heat_fluxes[group] = envelope(devc, [probe["hf"] for probe in probes])
    return {
        "time": devc["Time"],
        "temperatures": temperatures,
        "heat_fluxes": heat_fluxes,
        "hrr_time": hrr["Time"],
        "hrr": hrr["HRR"],
    }


def panel_plot(
    datasets: list[dict], labels: list[str], key: str, ylabel: str, title: str,
    output: Path, threshold: bool = False,
) -> None:
    fig, axes = plt.subplots(5, 4, figsize=(18, 19), constrained_layout=True)
    for ax, group in zip(axes.flat, GROUPS):
        for index, (dataset, label) in enumerate(zip(datasets, labels)):
            values = dataset[key].get(group)
            if values is None or not len(values):
                continue
            time = dataset["time"][: len(values)]
            ax.plot(time, values, color=COLORS[index], lw=1.35, label=label)
        if threshold:
            severe = CRITERIA[group]["severe"][0]
            ax.axhline(severe, color="#555555", lw=0.9, ls="--", label=f"重度阈值 {severe:g} C")
        ax.set_title(f"{group} | {GROUP_LABELS.get(group, group)}", fontsize=9)
        ax.set_xlabel("模拟时间（s）")
        ax.set_ylabel(ylabel)
        ax.grid(True, color="#d8dde3", lw=0.55)
        ax.legend(fontsize=6.5, loc="best")
    for ax in axes.flat[len(GROUPS) :]:
        ax.remove()
    fig.suptitle(title, fontsize=16)
    fig.savefig(output.with_suffix(".png"), dpi=180, facecolor="white")
    fig.savefig(output.with_suffix(".svg"), facecolor="white")
    plt.close(fig)


def plot_hrr(datasets: list[dict], labels: list[str], output: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(13, 9), constrained_layout=True)
    for index, (dataset, label) in enumerate(zip(datasets, labels)):
        axes[0].plot(dataset["hrr_time"], dataset["hrr"], color=COLORS[index], lw=1.4, label=label)
        mask = dataset["hrr_time"] <= 300.0
        axes[1].plot(dataset["hrr_time"][mask], dataset["hrr"][mask], color=COLORS[index], lw=1.4, label=label)
    axes[0].set_title("全域热释放速率")
    axes[1].set_title("全域热释放速率：前 300 s")
    for ax in axes:
        ax.set_xlabel("模拟时间（s）")
        ax.set_ylabel("HRR（kW）")
        ax.grid(True, color="#d8dde3", lw=0.6)
        ax.legend(fontsize=8)
    fig.savefig(output.with_suffix(".png"), dpi=180, facecolor="white")
    fig.savefig(output.with_suffix(".svg"), facecolor="white")
    plt.close(fig)


def plot_nominal_hrrpua(output: Path) -> None:
    values = [NOMINAL_HRRPUA.get(group, 0.0) for group in GROUPS]
    colors = ["#c85a17" if value else "#c8ced6" for value in values]
    fig, ax = plt.subplots(figsize=(14, 6), constrained_layout=True)
    bars = ax.bar(GROUPS, values, color=colors)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 4, f"{value:g}", ha="center", va="bottom", fontsize=8)
    ax.set_ylim(0, max(values) * 1.22)
    ax.set_ylabel("SURF 输入 HRRPUA 上限（kW/m2）")
    ax.set_title("当前材料 HRRPUA 输入上限（非时变实测输出）")
    ax.grid(True, axis="y", color="#d8dde3", lw=0.6)
    fig.savefig(output.with_suffix(".png"), dpi=180, facecolor="white")
    fig.savefig(output.with_suffix(".svg"), facecolor="white")
    plt.close(fig)


def write_summary(datasets: list[dict], labels: list[str], output: Path) -> None:
    with output.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(["case", "group", "latest_time_s", "peak_temperature_C", "peak_net_surface_heat_flux_kW_m2", "nominal_HRRPUA_kW_m2"])
        for dataset, label in zip(datasets, labels):
            for group in GROUPS:
                temp = dataset["temperatures"].get(group)
                flux = dataset["heat_fluxes"].get(group)
                writer.writerow([
                    label,
                    group,
                    float(dataset["time"][-1]),
                    float(np.nanmax(temp)) if temp is not None else "",
                    float(np.nanmax(flux)) if flux is not None else "",
                    NOMINAL_HRRPUA.get(group, 0.0),
                ])


def main() -> None:
    setup_plot_style()
    snapshot = ROOT / "outputs" / "live_HRRupper_thickness_monitor"
    snapshot.mkdir(parents=True, exist_ok=True)
    names = [
        "Q0050_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRupper_thickness_audit",
        "Q0200_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRupper_thickness_audit",
        "Q0400_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRupper_thickness_audit",
    ]
    case_dirs = [ROOT / "cases_adaptive" / name for name in names]
    labels = ["Q=50 J/cm2", "Q=200 J/cm2", "Q=400 J/cm2"]
    available = [(case_dir, label) for case_dir, label in zip(case_dirs, labels)
                 if list(case_dir.glob("*_devc.csv")) and list(case_dir.glob("*_hrr.csv"))]
    if not available:
        raise FileNotFoundError("No active-campaign DEVC/HRR snapshots are available")
    case_dirs, labels = map(list, zip(*available))
    datasets = [load_case(case_dir) for case_dir in case_dirs]
    panel_plot(datasets, labels, "temperatures", "有效探针最大壁面温度（C）",
               "当前方案各材料与设备最大温度包络",
               snapshot / "material_temperature_envelopes", threshold=True)
    panel_plot(datasets, labels, "heat_fluxes", "有效探针最大净表面热流（kW/m2）",
               "当前方案各材料与设备净表面热流包络",
               snapshot / "material_net_surface_heat_flux_envelopes")
    plot_hrr(datasets, labels, snapshot / "whole_domain_hrr")
    plot_nominal_hrrpua(snapshot / "nominal_material_hrrpua_inputs")
    write_summary(datasets, labels, snapshot / "curve_peak_summary.csv")
    print(snapshot)


if __name__ == "__main__":
    main()

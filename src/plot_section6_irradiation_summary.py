#!/usr/bin/env python3
"""Plot the corrected Section 6 DDA irradiation summary."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUT = Path(r"D:\Pyrosim\飞机模型\reports\徐宇涵_进展汇报\20260719")
PLANE_PEAK = 757.1
Q = 50.0

ANGLES = ["el=15°", "el=30°", "el=45°"]
ANGLE_FACES = [1912, 1434, 1344]
ANGLE_PEAKS = [735.0, 647.0, 529.0]

MATERIALS = [
    ("RADM", "雷达罩", 386, 735),
    ("WINS", "舷窗", 213, 677),
    ("BED", "床垫", 99, 441),
    ("CURT", "窗帘", 267, 618),
    ("U4", "仪表设备", 0, 0),
    ("SEAT", "座椅", 92, 618),
    ("AL2024", "蒙皮", 674, 735),
    ("AL5052", "风管", 0, 0),
    ("AL7075", "隔框", 121, 735),
    ("O2TANK", "氧气瓶", 10, 529),
    ("H1", "导航子系统", 5, 735),
    ("H2", "任务子系统", 37, 735),
    ("H3", "显示子系统", 0, 0),
    ("H4", "通信子系统", 4, 118),
    ("H5", "电池", 4, 618),
    ("H6", "电力传输", 0, 0),
    ("H7", "操纵子系统", 0, 0),
]


def setup() -> None:
    plt.rcParams.update({
        "font.family": "Microsoft YaHei",
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "font.size": 10,
        "axes.titleweight": "bold",
        "axes.edgecolor": "#94a3b8",
        "axes.labelcolor": "#334155",
        "xtick.color": "#475569",
        "ytick.color": "#475569",
    })


def finish(fig, name: str) -> None:
    fig.savefig(OUT / name, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def angle_chart() -> None:
    fluence = [peak / PLANE_PEAK * Q for peak in ANGLE_PEAKS]
    x = np.arange(len(ANGLES))
    fig, ax = plt.subplots(figsize=(8.2, 4.7))
    bars = ax.bar(x, ANGLE_FACES, width=0.52, color="#2f6f8f", label="DDA受照体素面数")
    ax.set_ylabel("受照体素面数")
    ax.set_xticks(x, ANGLES)
    ax.grid(axis="y", color="#dbe4ea", linewidth=0.8)
    ax.set_axisbelow(True)
    for bar, value in zip(bars, ANGLE_FACES):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 35, f"{value:,}", ha="center", color="#1e3a4a")
    ax2 = ax.twinx()
    ax2.plot(x, fluence, color="#c2412d", marker="o", linewidth=2.3, label="最大局部积分光冲量")
    ax2.set_ylabel("最大局部积分光冲量（J/cm²）")
    ax2.set_ylim(0, 55)
    for xx, value in zip(x, fluence):
        ax2.text(xx, value + 1.8, f"{value:.1f}", ha="center", color="#9f2f21", weight="bold")
    handles = [bars, ax2.lines[0]]
    ax.legend(handles, [h.get_label() for h in handles], loc="upper right", frameon=False)
    ax.set_title("不同俯仰角的DDA受照规模与最大局部光冲量\nQ=50 J/cm²，W=100 kt，az=270°")
    finish(fig, "section6_angle_exposure_fluence.png")


def material_bar_chart() -> None:
    labels = [f"{code} {name}" for code, name, _, _ in MATERIALS][::-1]
    faces = [row[2] for row in MATERIALS][::-1]
    peaks = [row[3] for row in MATERIALS][::-1]
    colors = ["#2b8a6e" if value > 0 else "#cbd5e1" for value in faces]
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 7.0), gridspec_kw={"wspace": 0.35})
    y = np.arange(len(labels))
    axes[0].barh(y, faces, color=colors)
    axes[0].set_yticks(y, labels)
    axes[0].set_xlabel("DDA受照体素面数")
    axes[0].set_title("各材料/设备直接受照规模")
    axes[0].grid(axis="x", color="#e2e8f0")
    axes[0].set_axisbelow(True)
    for yy, value in zip(y, faces):
        axes[0].text(value + 10, yy, str(value), va="center", fontsize=8)
    colors2 = ["#d28b27" if value > 0 else "#cbd5e1" for value in peaks]
    axes[1].barh(y, peaks, color=colors2)
    axes[1].set_yticks(y, [""] * len(y))
    axes[1].set_xlabel("Q=50局部峰值热流（kW/m²）")
    axes[1].set_title("各材料/设备最大局部峰值")
    axes[1].set_xlim(0, 820)
    axes[1].axvline(PLANE_PEAK, color="#b42318", linestyle="--", linewidth=1.4,
                    label=f"入射平面峰值 {PLANE_PEAK:.1f}")
    axes[1].grid(axis="x", color="#e2e8f0")
    axes[1].set_axisbelow(True)
    axes[1].legend(frameon=False, loc="lower right")
    for yy, value in zip(y, peaks):
        axes[1].text(value + 12, yy, str(value), va="center", fontsize=8)
    fig.suptitle("az=270°、el=15°下17组材料/设备的外部热流覆盖", fontsize=14, weight="bold")
    finish(fig, "section6_material_faces_peakflux.png")


def exposure_scatter() -> None:
    fig, ax = plt.subplots(figsize=(8.2, 5.2))
    offsets = {
        "H1": (8, 10), "H2": (8, -15), "AL7075": (8, 10), "RADM": (8, -15),
        "AL2024": (8, 8), "H5": (8, 8), "SEAT": (8, 8), "O2TANK": (8, 8),
    }
    for code, name, faces, peak in MATERIALS:
        if faces == 0:
            continue
        ax.scatter(faces, peak, s=65, color="#1b7f79", edgecolor="white", linewidth=0.6, zorder=3)
        ax.annotate(code, (faces, peak), xytext=offsets.get(code, (6, 5)),
                    textcoords="offset points", fontsize=8)
    ax.axhline(PLANE_PEAK, color="#b42318", linestyle="--", linewidth=1.4,
               label=f"入射平面峰值 {PLANE_PEAK:.1f} kW/m²")
    ax.set_xlabel("DDA受照体素面数")
    ax.set_ylabel("最大局部峰值热流（kW/m²）")
    ax.set_title("受照面积与局部峰值热流的关系\n受照面数反映覆盖范围，峰值反映最强局部载荷")
    ax.grid(color="#e2e8f0")
    ax.set_axisbelow(True)
    ax.legend(frameon=False)
    shielded = "当前角度无直达外部热流：U4、AL5052、H3、H6、H7"
    ax.text(0.50, 0.04, shielded, transform=ax.transAxes, fontsize=8.5, color="#475569",
            bbox={"boxstyle": "round,pad=0.45", "facecolor": "#f1f5f9", "edgecolor": "#cbd5e1"})
    finish(fig, "section6_faces_vs_peakflux.png")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    setup()
    angle_chart()
    material_bar_chart()
    exposure_scatter()
    for path in sorted(OUT.glob("section6_*.png")):
        print(path)


if __name__ == "__main__":
    main()

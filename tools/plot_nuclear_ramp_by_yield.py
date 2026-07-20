#!/usr/bin/env python3
"""Plot the normalized nuclear thermal pulse F(t) for several yields."""

from __future__ import annotations

import csv
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_FDS = (
    ROOT / "cases" / "Q0400_W0100_az270_el15_H1H7_v2"
    / "Q0400_W0100_az270_el15_H1H7_v2.fds"
)
OUT_DIR = ROOT / "figures"
YIELDS_KT = (1, 20, 100, 1000)
I_NORM_REFERENCE = 2.1764


def read_nuclear_ramp(path: Path) -> tuple[np.ndarray, np.ndarray]:
    text = path.read_text(encoding="utf-8", errors="replace")
    points = re.findall(
        r"&RAMP\s+ID='NUCLEAR_RAMP',\s*T=([0-9.Ee+-]+),\s*F=([0-9.Ee+-]+)",
        text,
    )
    if len(points) < 3:
        raise ValueError(f"No usable NUCLEAR_RAMP found in {path}")
    values = np.asarray(points, dtype=float)
    return values[:, 0], values[:, 1]


def peak_time(yield_kt: float) -> float:
    return 0.044 * yield_kt**0.42


def main() -> None:
    template_t, shape = read_nuclear_ramp(TEMPLATE_FDS)
    peak_index = int(np.argmax(shape))
    template_peak = template_t[peak_index]
    tau = template_t / template_peak
    i_norm = float(np.trapz(shape, tau))
    if not np.isclose(i_norm, I_NORM_REFERENCE, rtol=5e-4):
        raise ValueError(f"Unexpected normalized area: {i_norm:.6f}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    colors = ["#295F98", "#16877A", "#D17A16", "#B33A3A"]
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 5.4), constrained_layout=True)

    summary = []
    for yield_kt, color in zip(YIELDS_KT, colors):
        t_peak = peak_time(yield_kt)
        physical_t = tau * t_peak
        effective_width = i_norm * t_peak
        end_time = physical_t[-2]  # Last point is a redundant F=0 terminator.
        label = f"{yield_kt:g} kt  ($t_{{max}}$={t_peak:.3f} s)"
        axes[0].plot(physical_t, shape, lw=2.2, color=color, label=label)
        axes[0].scatter([t_peak], [1.0], color=color, s=28, zorder=3)
        axes[1].plot(tau, shape, lw=2.2, color=color, label=f"{yield_kt:g} kt")
        summary.append((yield_kt, t_peak, end_time, effective_width, i_norm))

    axes[0].set_title("Physical-time pulse broadening")
    axes[0].set_xlabel("Time, $t$ (s)")
    axes[0].set_ylabel("Normalized irradiance, $F(t)$")
    axes[0].set_xlim(left=0)
    axes[0].set_ylim(0, 1.08)
    axes[0].legend(frameon=False, fontsize=9)

    axes[1].set_title("Common dimensionless pulse shape")
    axes[1].set_xlabel(r"Normalized time, $\tau=t/t_{max}$")
    axes[1].set_ylabel(r"$F(\tau)$")
    axes[1].set_xlim(0, 16)
    axes[1].set_ylim(0, 1.08)
    axes[1].text(
        0.97,
        0.94,
        rf"$\int F(\tau)d\tau={i_norm:.4f}$",
        transform=axes[1].transAxes,
        ha="right",
        va="top",
        fontsize=10,
    )

    for ax in axes:
        ax.grid(True, color="#D7DCE2", linewidth=0.8, alpha=0.8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=9)

    fig.suptitle(
        r"Nuclear thermal-pulse history by yield: $t_{max}=0.044W^{0.42}$",
        fontsize=14,
    )
    fig.savefig(OUT_DIR / "nuclear_ramp_Ft_by_yield.png", dpi=300, facecolor="white")
    fig.savefig(OUT_DIR / "nuclear_ramp_Ft_by_yield.svg", facecolor="white")
    plt.close(fig)

    with (OUT_DIR / "nuclear_ramp_Ft_by_yield.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["yield_kt", "t_max_s", "pulse_end_s", "effective_width_s", "I_norm"])
        writer.writerows(summary)

    print(f"Template points: {len(shape)}")
    print(f"Template t_max: {template_peak:.6f} s")
    print(f"Normalized area: {i_norm:.6f}")
    for row in summary:
        print(f"W={row[0]:g} kt: t_max={row[1]:.6f} s, end={row[2]:.6f} s, width={row[3]:.6f} s")


if __name__ == "__main__":
    main()

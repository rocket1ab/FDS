#!/usr/bin/env python3
"""Plot the DDA-derived external heat-flux distribution on aircraft voxel faces."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASE = ROOT / "cases_probe_corrected" / "Q0100_W0100_az270_el15_H1H7_v6_probe_fixed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, default=DEFAULT_CASE)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "external_heat_flux_3d_dda_q100.png")
    return parser.parse_args()


def parse_obstacle_centres(fds_path: Path, limit: int = 12000) -> np.ndarray:
    text = fds_path.read_text(encoding="utf-8", errors="replace")
    pattern = r"\bXB\s*=\s*" + r"\s*,\s*".join([r"([-+0-9.eE]+)"] * 6)
    points = []
    for match in re.finditer(r"&OBST\b(.*?)/", text, flags=re.DOTALL | re.IGNORECASE):
        xb = re.search(pattern, match.group(1), flags=re.IGNORECASE)
        if not xb:
            continue
        values = [float(xb.group(i)) for i in range(1, 7)]
        points.append([(values[0] + values[1]) / 2, (values[2] + values[3]) / 2, (values[4] + values[5]) / 2])
    cloud = np.asarray(points, dtype=float)
    if len(cloud) > limit:
        cloud = cloud[np.linspace(0, len(cloud) - 1, limit, dtype=int)]
    return cloud


def voxel_quad(row: pd.Series, size: float = 0.094) -> list[tuple[float, float, float]]:
    x, y, z = float(row.x), float(row.y), float(row.z)
    half = size / 2
    if row.face in {"-x", "+x"}:
        return [(x, y - half, z - half), (x, y + half, z - half),
                (x, y + half, z + half), (x, y - half, z + half)]
    if row.face in {"-y", "+y"}:
        return [(x - half, y, z - half), (x + half, y, z - half),
                (x + half, y, z + half), (x - half, y, z + half)]
    return [(x - half, y - half, z), (x + half, y - half, z),
            (x + half, y + half, z), (x - half, y + half, z)]


def equalize_3d_axes(ax, limits: tuple[tuple[float, float], ...]) -> None:
    spans = [hi - lo for lo, hi in limits]
    ax.set_box_aspect(spans)
    ax.set_xlim(*limits[0])
    ax.set_ylim(*limits[1])
    ax.set_zlim(*limits[2])


def main() -> None:
    args = parse_args()
    case_dir = args.case_dir.resolve()
    flux = pd.read_csv(case_dir / "flux_faces.csv")
    summary = json.loads((case_dir / "case_summary.json").read_text(encoding="utf-8"))
    fds_path = next(case_dir.glob("*.fds"))
    aircraft = parse_obstacle_centres(fds_path)

    font_path = Path(r"C:\Windows\Fonts\msyh.ttc")
    if font_path.exists():
        mpl.font_manager.fontManager.addfont(str(font_path))
        mpl.rcParams["font.family"] = mpl.font_manager.FontProperties(fname=str(font_path)).get_name()
    mpl.rcParams.update({
        "font.size": 10,
        "axes.edgecolor": "#718096",
        "axes.labelcolor": "#263238",
        "xtick.color": "#4b5563",
        "ytick.color": "#4b5563",
        "figure.facecolor": "white",
    })

    values = flux["external_flux_kw_m2"].to_numpy(float)
    norm = mpl.colors.Normalize(vmin=0, vmax=float(summary["plane_peak_irradiance_kw_m2"]))
    cmap = mpl.colormaps["turbo"]
    quads = [voxel_quad(row) for _, row in flux.iterrows()]

    fig = plt.figure(figsize=(16, 9), constrained_layout=True)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor("#f7f9fb")

    if len(aircraft):
        ax.scatter(
            aircraft[:, 0], aircraft[:, 1], aircraft[:, 2],
            s=1.2, color="#718096", alpha=0.055, depthshade=False,
            label="Aircraft OBST geometry",
        )

    collection = Poly3DCollection(
        quads,
        facecolors=cmap(norm(values)),
        edgecolors="none",
        linewidths=0,
        alpha=0.98,
        zsort="average",
    )
    ax.add_collection3d(collection)

    # az=270 deg, el=15 deg: source lies toward -X and +Z; radiation travels +X and -Z.
    arrow_start = np.array([-0.9, 0.0, 2.7])
    incoming = np.array([np.cos(np.deg2rad(15)), 0.0, -np.sin(np.deg2rad(15))])
    ax.quiver(*arrow_start, *(incoming * 2.0), color="#20262e", linewidth=2.0,
              arrow_length_ratio=0.13)
    ax.text(*(arrow_start + incoming * 0.85 + np.array([0, 0.08, 0.12])),
            "Incident radiation", color="#20262e", fontsize=10)

    max_index = int(np.argmax(values))
    max_row = flux.iloc[max_index]
    ax.scatter([max_row.x], [max_row.y], [max_row.z], s=38, marker="o",
               facecolor="none", edgecolor="#111827", linewidth=1.2, depthshade=False)

    ax.set_title(
        "外部热流三维分布（体素法 DDA 追踪结果）\n"
        f"Q={summary['Q_J_cm2']} J/cm², W={summary['yield_kt']} kt, "
        f"az={summary['azimuth_deg']}°, el={summary['elevation_deg']}°",
        fontsize=16, weight="bold", pad=18,
    )
    ax.set_xlabel("X / 机身纵向 (m)", labelpad=10)
    ax.set_ylabel("Y / 横向 (m)", labelpad=10)
    ax.set_zlabel("Z / 垂向 (m)", labelpad=10)
    ax.view_init(elev=23, azim=-61)
    equalize_3d_axes(ax, ((-1.1, 10.4), (-2.0, 2.0), (-2.4, 3.0)))
    ax.grid(True, linewidth=0.45, alpha=0.45)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_facecolor((0.97, 0.98, 0.99, 0.45))
        axis.pane.set_edgecolor((0.75, 0.79, 0.83, 0.6))

    scalar = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
    scalar.set_array(values)
    cbar = fig.colorbar(scalar, ax=ax, shrink=0.70, pad=0.035, aspect=28)
    cbar.set_label("峰值外部热流 (kW/m²)", labelpad=10)
    cbar.ax.axhline(values.max(), color="#111827", linewidth=1.0)
    cbar.ax.text(1.35, norm(values.max()), f"max {values.max():.0f}",
                 transform=cbar.ax.transAxes, va="center", color="#111827")

    fig.text(
        0.012, 0.012,
        f"受照体素面: {len(flux):,}  |  局部热流: {values.min():.0f}-{values.max():.0f} kW/m²  |  "
        f"入射平面峰值: {summary['plane_peak_irradiance_kw_m2']:.1f} kW/m²  |  网格面片: 0.1 m",
        color="#4b5563", fontsize=9,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=240, bbox_inches="tight", facecolor="white")
    fig.savefig(args.output.with_suffix(".svg"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(json.dumps({
        "case": summary["case"],
        "faces": len(flux),
        "min_kw_m2": float(values.min()),
        "max_kw_m2": float(values.max()),
        "png": str(args.output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

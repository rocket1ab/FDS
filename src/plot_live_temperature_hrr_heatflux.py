#!/usr/bin/env python3
"""Plot live material temperature, surface heat flux, and global HRR snapshots."""
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

# These are input maxima from the current SURF definitions, not measured outputs.
NOMINAL_HRRPUA = {
    "RADM": 75.0,
    "WINS": 250.0,
    "BED": 180.0,
    "CURT": 180.0,
    "U4": 100.0,
    "SEAT": 200.0,
    "H6": 200.0,
    "H7": 180.0,
}


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
            ax.axhline(severe, color="#555555", lw=0.9, ls="--", label=f"Severe {severe:g} C")
        ax.set_title(f"{group} | {CRITERIA[group]['label']}", fontsize=9)
        ax.set_xlabel("Simulation time (s)")
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
    axes[0].set_title("Whole-domain heat release rate")
    axes[1].set_title("Whole-domain heat release rate: first 300 s")
    for ax in axes:
        ax.set_xlabel("Simulation time (s)")
        ax.set_ylabel("HRR (kW)")
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
    ax.set_ylabel("Specified maximum HRRPUA (kW/m2)")
    ax.set_title("Current SURF HRRPUA inputs (not time-resolved measured output)")
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
    snapshot = ROOT / "outputs" / "live_material_curves_20260722"
    case_dirs = [
        snapshot / "Q0100_W0100_az270_el15_H1H7_v5_Qnorm_adapt_thickness_audit",
        snapshot / "Q0200_W0100_az270_el15_H1H7_v5_Qnorm_adapt_thickness_audit",
        snapshot / "Q0400_W0100_az270_el15_H1H7_v5_Qnorm_threshold",
    ]
    labels = ["Q100 audited thickness", "Q200 audited thickness", "Q400 preserved old thickness"]
    datasets = [load_case(case_dir) for case_dir in case_dirs]
    panel_plot(datasets, labels, "temperatures", "Maximum valid-probe wall temperature (C)",
               "Live maximum wall-temperature envelopes by material/equipment",
               snapshot / "material_temperature_envelopes", threshold=True)
    panel_plot(datasets, labels, "heat_fluxes", "Maximum valid-probe net surface heat flux (kW/m2)",
               "Live net surface heat-flux envelopes by material/equipment",
               snapshot / "material_net_surface_heat_flux_envelopes")
    plot_hrr(datasets, labels, snapshot / "whole_domain_hrr")
    plot_nominal_hrrpua(snapshot / "nominal_material_hrrpua_inputs")
    write_summary(datasets, labels, snapshot / "curve_peak_summary.csv")
    print(snapshot)


if __name__ == "__main__":
    main()

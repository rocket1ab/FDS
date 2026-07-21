#!/usr/bin/env python3
"""Plot live maximum-probe temperature envelopes for H1-H7 cases."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CRITERIA = json.loads((ROOT / "config" / "damage_criteria.json").read_text(encoding="utf-8"))["groups"]


def read_devc(path: Path) -> dict[str, np.ndarray]:
    rows = list(csv.reader(path.open(encoding="utf-8-sig", errors="replace")))
    start = next(i for i, row in enumerate(rows) if row and row[0].strip().strip('"').lower() == "time")
    header = [cell.strip().strip('"') for cell in rows[start]]
    values = []
    for row in rows[start + 1 :]:
        if len(row) < len(header):
            continue
        try:
            values.append([float(cell) for cell in row[: len(header)]])
        except ValueError:
            continue
    data = np.asarray(values, dtype=float)
    return {name: data[:, i] for i, name in enumerate(header)}


def load_case(case_dir: Path) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    registry = json.loads((case_dir / "monitor_registry.json").read_text(encoding="utf-8"))
    devc = next(case_dir.glob("*_devc.csv"))
    columns = read_devc(devc)
    times = columns["Time"]
    envelopes = {}
    for group in CRITERIA:
        names = [item["wt"] for item in registry.get(group, []) if item["wt"] in columns]
        if names:
            stack = np.vstack([columns[name] for name in names])
            envelopes[group] = np.nanmax(stack, axis=0)
    return times, envelopes


def plot(case_dirs: list[Path], labels: list[str], output: Path) -> None:
    datasets = [load_case(case_dir) for case_dir in case_dirs]
    groups = list(CRITERIA)
    fig, axes = plt.subplots(5, 4, figsize=(18, 19), constrained_layout=True)
    colors = ["#b42318", "#1565a7", "#0f766e", "#7a5a00"]

    for ax, group in zip(axes.flat, groups):
        criterion = CRITERIA[group]
        for index, ((times, envelopes), label) in enumerate(zip(datasets, labels)):
            values = envelopes.get(group)
            if values is None:
                continue
            ax.plot(times, values, lw=1.5, color=colors[index % len(colors)], label=label)
            peak_index = int(np.nanargmax(values))
            ax.scatter(times[peak_index], values[peak_index], s=18, color=colors[index % len(colors)], zorder=3)
        severe_temperature = criterion["severe"][0]
        ax.axhline(severe_temperature, color="#555555", ls="--", lw=1.0,
                   label=f"Severe {severe_temperature:g} C")
        ax.set_title(f"{group} | {criterion['label']}", fontsize=10)
        ax.set_xlabel("Simulation time (s)")
        ax.set_ylabel("Max probe wall temperature (C)")
        ax.grid(True, color="#dddddd", lw=0.6)
        ax.legend(fontsize=7, loc="best")

    for ax in axes.flat[len(groups) :]:
        ax.remove()
    fig.suptitle("Live material/equipment temperature envelopes", fontsize=16)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=170, facecolor="white")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_dirs", nargs="+", type=Path)
    parser.add_argument("--labels", nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    labels = args.labels or [case_dir.name for case_dir in args.case_dirs]
    if len(labels) != len(args.case_dirs):
        raise SystemExit("--labels must match the number of case directories")
    plot([path.resolve() for path in args.case_dirs], labels, args.output.resolve())


if __name__ == "__main__":
    main()

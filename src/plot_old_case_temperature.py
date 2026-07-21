#!/usr/bin/env python3
"""Plot wall-temperature histories from the clean legacy Q400 archive."""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
from pathlib import Path

import matplotlib.pyplot as plt


GROUPS = {
    "RADM": ("Radome", 400.0, 180.0),
    "WINS": ("PMMA windows", 250.0, 8.0),
    "BED": ("Nylon mattress", 500.0, 5.0),
    "CURT": ("Nylon curtain", 500.0, 5.0),
    "INST": ("Instrument panel", 400.0, 5.0),
    "SEAT": ("PU seats", 500.0, 5.0),
    "AL2024": ("Al 2024 skin", 400.0, 60.0),
    "AL5052": ("Al 5052 duct", 400.0, 60.0),
    "AL7075": ("Al 7075 frame", 400.0, 60.0),
    "O2TANK": ("Oxygen tank", 400.0, 60.0),
}


def read_devc(path: Path) -> tuple[list[float], dict[str, list[float]]]:
    text = path.read_bytes().replace(b"\x00", b"").decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    header_index = next(
        i for i, row in enumerate(rows)
        if row and row[0].strip().strip('"').lower() == "time"
    )
    header = [cell.strip().strip('"') for cell in rows[header_index]]
    numeric: list[list[float]] = []
    for row in rows[header_index + 1:]:
        if len(row) < len(header):
            continue
        try:
            numeric.append([float(value) for value in row[:len(header)]])
        except ValueError:
            continue
    columns = {name: [row[i] for row in numeric] for i, name in enumerate(header)}
    return columns["Time"], columns


def longest_above(times: list[float], values: list[float], threshold: float) -> float:
    best = 0.0
    start = None
    for time, value in zip(times, values):
        if math.isfinite(value) and value >= threshold:
            start = time if start is None else start
            best = max(best, time - start)
        else:
            start = None
    return best


def build_series(times: list[float], columns: dict[str, list[float]]) -> dict:
    result = {}
    for group, (label, threshold, required) in GROUPS.items():
        pattern = re.compile(rf"D_\d+_\d+_{group}_WT$")
        names = [name for name in columns if pattern.match(name)]
        probes = [columns[name] for name in names]
        envelope = [max(values) for values in zip(*probes)]
        result[group] = {
            "label": label,
            "threshold_C": threshold,
            "required_s": required,
            "probe_names": names,
            "probes": probes,
            "envelope": envelope,
            "peak_C": max(envelope),
            "continuous_s": longest_above(times, envelope, threshold),
        }
    return result


def plot(times: list[float], series: dict, destination: Path) -> None:
    plt.rcParams.update({"font.size": 9, "axes.titleweight": "normal"})
    fig, axes = plt.subplots(5, 2, figsize=(15, 16), sharex=True, constrained_layout=True)
    for axis, (group, item) in zip(axes.flat, series.items()):
        for values in item["probes"]:
            axis.plot(times, values, color="#a7adb4", linewidth=0.65, alpha=0.55)
        color = "#087f8c" if group in {"RADM", "WINS", "BED", "CURT", "INST", "SEAT"} else "#305f8d"
        axis.plot(times, item["envelope"], color=color, linewidth=1.8, label="Dynamic maximum")
        axis.axhline(item["threshold_C"], color="#ba2d0b", linestyle="--", linewidth=1.1,
                     label=f"Severe {item['threshold_C']:.0f} C")
        passed = item["continuous_s"] >= item["required_s"]
        axis.set_title(
            f"{group} | {item['label']} | peak {item['peak_C']:.1f} C | "
            f">= threshold {item['continuous_s']:.1f}/{item['required_s']:.0f} s | "
            f"{'SEVERE' if passed else 'NOT SEVERE'}",
            loc="left",
        )
        axis.set_xlim(0, 1500)
        axis.set_ylim(0, max(item["peak_C"] * 1.08, item["threshold_C"] * 1.25))
        axis.grid(True, color="#d9dde2", linewidth=0.6, alpha=0.8)
        axis.set_ylabel("Wall temperature (C)")
        axis.legend(loc="upper right", frameon=False, fontsize=8)
    for axis in axes[-1]:
        axis.set_xlabel("Simulation time (s)")
    fig.suptitle(
        "Legacy Q0400_BA0_coat_T1500_v4: wall temperature histories",
        fontsize=14,
        fontweight="normal",
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=180)
    plt.close(fig)


def write_visual_data(times: list[float], series: dict, destination: Path) -> None:
    stride = max(1, math.ceil(len(times) / 420))
    payload = {
        "time": [round(value, 3) for value in times[::stride]],
        "groups": {
            group: {
                "label": item["label"],
                "threshold_C": item["threshold_C"],
                "required_s": item["required_s"],
                "peak_C": round(item["peak_C"], 2),
                "continuous_s": round(item["continuous_s"], 2),
                "temperature_C": [round(value, 2) for value in item["envelope"][::stride]],
            }
            for group, item in series.items()
        },
    }
    destination.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()
    devc = next(args.case_dir.glob("*_devc.csv"))
    times, columns = read_devc(devc)
    series = build_series(times, columns)
    plot(times, series, args.png)
    write_visual_data(times, series, args.json)
    print(json.dumps({
        group: {
            "peak_C": round(item["peak_C"], 1),
            "continuous_s": round(item["continuous_s"], 1),
            "severe": item["continuous_s"] >= item["required_s"],
        }
        for group, item in series.items()
    }, indent=2))


if __name__ == "__main__":
    main()

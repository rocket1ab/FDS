#!/usr/bin/env python3
"""Score candidate plane-radiation angles against all monitored groups."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

import build_cases as B
import voxel_core as V


ROOT = Path(__file__).resolve().parents[1]
TARGETS = {"BED", "RADM", "U4", "AL2024", "AL5052", "AL7075", "O2TANK",
           "H1", "H2", "H4", "H5", "H6", "H7"}


def percentile(values: list[float], q: float) -> float:
    return float(np.percentile(values, q)) if values else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--azimuths", default="0,45,90,135,180,225,270,315")
    parser.add_argument("--elevations", default="5,15,30,45,60")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "incident_angle_scan.csv")
    args = parser.parse_args()
    azimuths = [float(value) for value in args.azimuths.split(",")]
    elevations = [float(value) for value in args.elevations.split(",")]

    base = B.prepare_physics_base()
    parsed, obstacles = B.parse_geometry(base)
    domain = V.get_mesh_domain(parsed)
    opaque, glass, grid = V.build_voxel_grids(obstacles, domain)
    groups = list(json.loads((ROOT / "config" / "damage_criteria.json").read_text(encoding="utf-8"))["groups"])
    rows = []
    for azimuth in azimuths:
        for elevation in elevations:
            direction = V.sun_vec(azimuth, elevation)
            values = defaultdict(list)
            for obstacle in obstacles:
                if not obstacle["flux_recv"]:
                    continue
                group = B.group_for(obstacle)
                if not group:
                    continue
                records = V.compute_obst_flux(obstacle, direction, 1000.0, opaque, glass, grid)
                values[group].extend(float(flux) for _, _, flux in records if flux > 0)
            maxima = {group: max(values[group], default=0.0) for group in groups}
            p90 = {group: percentile(values[group], 90) for group in groups}
            target_positive = [p90[group] for group in TARGETS if p90[group] > 0]
            all_positive = [p90[group] for group in groups if p90[group] > 0]
            rows.append({
                "azimuth_deg": azimuth,
                "elevation_deg": elevation,
                "direct_groups": sum(maxima[group] > 0 for group in groups),
                "direct_target_groups": sum(maxima[group] > 0 for group in TARGETS),
                "min_positive_target_p90": min(target_positive, default=0.0),
                "mean_target_p90": float(np.mean(target_positive)) if target_positive else 0.0,
                "mean_all_p90": float(np.mean(all_positive)) if all_positive else 0.0,
                **{f"{group}_max": maxima[group] for group in groups},
                **{f"{group}_p90": p90[group] for group in groups},
            })
            print(json.dumps({key: rows[-1][key] for key in (
                "azimuth_deg", "elevation_deg", "direct_groups", "direct_target_groups",
                "min_positive_target_p90", "mean_target_p90")}, ensure_ascii=False))

    rows.sort(key=lambda row: (
        row["direct_target_groups"], row["direct_groups"],
        row["min_positive_target_p90"], row["mean_target_p90"]), reverse=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("BEST", json.dumps(rows[0], ensure_ascii=False))


if __name__ == "__main__":
    main()

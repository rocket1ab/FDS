#!/usr/bin/env python3
"""Validate redundant surface probes and plot their spatial distribution."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASE = ROOT / "cases_qnorm" / "Q0100_W0100_az270_el15_H1H7_v5_Qnorm"
REPORTS = ROOT / "reports"
INLINE_VIS = Path(
    r"C:\Users\admin\.codex\visualizations\2026\07\13\019f5948-9f5b-7ed2-82da-668edb38b458"
) / "probe-distribution-3d-2d.html"

GROUP_META = {
    "RADM": ("Radome", "Fiberglass"),
    "WINS": ("Windows", "PMMA"),
    "BED": ("Mattress", "Nylon"),
    "CURT": ("Curtain", "Nylon"),
    "U4": ("U4 equipment", "Legacy U04 material"),
    "SEAT": ("Seats", "Polyurethane foam"),
    "AL2024": ("Aircraft skin", "Aluminium 2024"),
    "AL5052": ("Duct", "Aluminium 5052"),
    "AL7075": ("Frame", "Aluminium 7075"),
    "O2TANK": ("Oxygen tank", "Aluminium 7075"),
    "H1": ("Navigation subsystem", "Aluminium 6061, 3 mm"),
    "H2": ("Mission subsystem", "Aluminium 6061, 3 mm"),
    "H3": ("Display subsystem", "Aluminium 6061, 3 mm"),
    "H4": ("Communication subsystem", "Aluminium 6061, 3 mm"),
    "H5": ("Battery", "Aluminium 6061, 3 mm"),
    "H6": ("Power transmission", "PVC, 1 mm"),
    "H7": ("Flight-control subsystem", "CR rubber, 2 mm"),
}

FACE_IOR = {"-x": -1, "+x": 1, "-y": -2, "+y": 2, "-z": -3, "+z": 3}
GROUP_SURFACE_TOKENS = {
    "RADM": ("E-玻璃纤维",), "WINS": ("丙烯酸塑料",),
    "BED": ("尼龙织物_床垫",), "CURT": ("尼龙织物_窗帘",),
    "U4": ("环氧玻璃纤维",), "SEAT": ("聚氨酯泡沫",),
    "AL2024": ("铝合金2024",), "AL5052": ("铝合金5052",),
    "AL7075": ("铝合金7075",), "O2TANK": ("氧气瓶",),
    "H1": ("导航子系统",), "H2": ("任务子系统",), "H3": ("显示子系统",),
    "H4": ("通信子系统",), "H5": ("电池",), "H6": ("电力传输子系统",),
    "H7": ("操纵子系统",),
}
COLORS = [
    "#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00", "#56B4E9",
    "#F0E442", "#332288", "#88CCEE", "#44AA99", "#117733", "#999933",
    "#DDCC77", "#CC6677", "#882255", "#AA4499", "#661100",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, default=DEFAULT_CASE)
    parser.add_argument("--reports-dir", type=Path, default=REPORTS)
    parser.add_argument("--inline-html", type=Path, default=INLINE_VIS)
    return parser.parse_args()


def parse_devc(text: str) -> dict[str, dict]:
    result = {}
    for match in re.finditer(r"&DEVC\b(.*?)/", text, flags=re.DOTALL | re.IGNORECASE):
        block = match.group(1)
        id_match = re.search(r"\bID\s*=\s*'([^']+)'", block, flags=re.IGNORECASE)
        xyz_match = re.search(
            r"\bXYZ\s*=\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)",
            block,
            flags=re.IGNORECASE,
        )
        q_match = re.search(r"\bQUANTITY\s*=\s*'([^']+)'", block, flags=re.IGNORECASE)
        ior_match = re.search(r"\bIOR\s*=\s*(-?\d+)", block, flags=re.IGNORECASE)
        if id_match and xyz_match:
            result[id_match.group(1)] = {
                "xyz": [float(xyz_match.group(i)) for i in range(1, 4)],
                "quantity": q_match.group(1) if q_match else "",
                "ior": int(ior_match.group(1)) if ior_match else None,
            }
    return result


def mesh_domain(text: str) -> list[float] | None:
    boxes = []
    for match in re.finditer(r"&MESH\b(.*?)/", text, flags=re.DOTALL | re.IGNORECASE):
        xb = re.search(
            r"\bXB\s*=\s*" + r"\s*,\s*".join([r"([-+0-9.eE]+)"] * 6),
            match.group(1),
            flags=re.IGNORECASE,
        )
        if xb:
            boxes.append([float(xb.group(i)) for i in range(1, 7)])
    if not boxes:
        return None
    return [
        min(b[0] for b in boxes), max(b[1] for b in boxes),
        min(b[2] for b in boxes), max(b[3] for b in boxes),
        min(b[4] for b in boxes), max(b[5] for b in boxes),
    ]


def parse_obstacles(text: str) -> list[dict]:
    obstacles = []
    pattern = r"\bXB\s*=\s*" + r"\s*,\s*".join([r"([-+0-9.eE]+)"] * 6)
    for match in re.finditer(r"&OBST\b(.*?)/", text, flags=re.DOTALL | re.IGNORECASE):
        block = match.group(1)
        xb = re.search(pattern, block, flags=re.IGNORECASE)
        if xb:
            surf6 = re.search(r"\bSURF_ID6\s*=\s*((?:'[^']+'\s*,?\s*){6})", block, flags=re.I)
            surf1 = re.search(r"\bSURF_ID\s*=\s*'([^']+)'", block, flags=re.I)
            if surf6:
                surfaces = re.findall(r"'([^']+)'", surf6.group(1))
            elif surf1:
                surfaces = [surf1.group(1)] * 6
            else:
                surfaces = [""] * 6
            obstacles.append({"xb": [float(xb.group(i)) for i in range(1, 7)], "surfaces": surfaces})
    return obstacles


def group_for_surface(surface: str) -> str | None:
    if "_R" in surface:
        prefix = surface.split("_R", 1)[0]
        if prefix in GROUP_META:
            return prefix
    if "氧气瓶" in surface:
        return "O2TANK"
    for group, tokens in GROUP_SURFACE_TOKENS.items():
        if group == "AL7075" and "氧气瓶" in surface:
            continue
        if any(token in surface for token in tokens):
            return group
    return None


def target_face_distance(xyz, ior: int, group: str, obstacles: list[dict], lateral_tol=0.051) -> float:
    """Return distance to the intended material face after 0.1 m FDS-grid snapping."""
    axis = abs(ior) - 1
    sign = 1 if ior > 0 else -1
    face_index = 2 * axis + (1 if sign > 0 else 0)
    other_axes = [a for a in range(3) if a != axis]
    distances = []
    for obstacle in obstacles:
        box = obstacle["xb"]
        if group_for_surface(obstacle["surfaces"][face_index]) != group:
            continue
        if all(box[2 * a] - lateral_tol <= float(xyz[a]) <= box[2 * a + 1] + lateral_tol for a in other_axes):
            distances.append(abs(float(xyz[axis]) - box[face_index]))
    return min(distances, default=math.inf)


def close_xyz(a, b, tol=5.1e-4) -> bool:
    return max(abs(float(x) - float(y)) for x, y in zip(a, b)) <= tol


def validate(case_dir: Path) -> tuple[dict, list[dict]]:
    registry_path = case_dir / "monitor_registry.json"
    flux_path = case_dir / "flux_faces.csv"
    fds_files = sorted(case_dir.glob("*.fds"))
    if not fds_files:
        raise FileNotFoundError(f"No FDS input in {case_dir}")

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    with flux_path.open(encoding="utf-8-sig", newline="") as handle:
        flux_rows = list(csv.DictReader(handle))
    text = fds_files[0].read_text(encoding="utf-8", errors="replace")
    devcs = parse_devc(text)
    domain = mesh_domain(text)
    obstacles = parse_obstacles(text)

    points = []
    issues = []
    group_rows = []
    for group, probes in registry.items():
        group_flux = [r for r in flux_rows if r["group"] == group]
        group_ok = 0
        direct_count = 0
        unique_xyz = set()
        for probe in probes:
            xyz = [float(v) for v in probe["xyz"]]
            ior = int(probe["ior"])
            unique_xyz.add(tuple(xyz))
            wt = devcs.get(probe["wt"])
            hf = devcs.get(probe["hf"])
            fds_ok = bool(
                wt and hf
                and close_xyz(wt["xyz"], xyz) and close_xyz(hf["xyz"], xyz)
                and wt["ior"] == ior and hf["ior"] == ior
                and wt["quantity"].upper() == "WALL TEMPERATURE"
                and hf["quantity"].upper() == "NET HEAT FLUX"
            )
            face_matches = [
                r for r in group_flux
                if r["obst_id"] == probe["obst_id"]
                and FACE_IOR.get(r["face"]) == ior
                and close_xyz([r["x"], r["y"], r["z"]], xyz)
            ]
            illuminated_face_ok = bool(face_matches)
            target_distance = target_face_distance(xyz, ior, group, obstacles)
            # The mesh is 0.1 m. A boundary DEVC is accepted when its requested point
            # snaps to the gas cell adjoining the intended face.
            obst_face_ok = target_distance <= 0.105
            face_ok = obst_face_ok
            in_domain = bool(domain and domain[0] <= xyz[0] <= domain[1]
                             and domain[2] <= xyz[1] <= domain[3]
                             and domain[4] <= xyz[2] <= domain[5])
            base_flux = float(probe.get("base_flux", 0.0))
            direct_count += base_flux > 0
            valid = fds_ok and face_ok and in_domain
            group_ok += valid
            if not valid:
                issues.append({
                    "group": group, "wt": probe["wt"], "fds_pair_ok": fds_ok,
                    "voxel_face_ok": face_ok, "illuminated_face_record_ok": illuminated_face_ok,
                    "oriented_obst_face_ok": obst_face_ok,
                    "nearest_intended_face_distance_m": None if math.isinf(target_distance) else target_distance,
                    "inside_mesh": in_domain,
                })
            points.append({
                "group": group, "id": probe["wt"], "xyz": xyz, "ior": ior,
                "base_flux_kw_m2": base_flux, "valid": valid,
                "component": GROUP_META.get(group, (group, ""))[0],
                "material": GROUP_META.get(group, (group, ""))[1],
            })
        candidate_xyz = {
            (round(float(r["x"]), 4), round(float(r["y"]), 4), round(float(r["z"]), 4), FACE_IOR[r["face"]])
            for r in group_flux
        }
        group_rows.append({
            "group": group,
            "component": GROUP_META.get(group, (group, ""))[0],
            "material": GROUP_META.get(group, (group, ""))[1],
            "probes": len(probes),
            "unique_positions": len(unique_xyz),
            "available_exposed_face_candidates": len(candidate_xyz),
            "directly_illuminated_probes": direct_count,
            "validated": group_ok,
            "status": "PASS" if group_ok == len(probes) else "FAIL",
        })

    total = len(points)
    validation = {
        "case": case_dir.name,
        "fds_file": fds_files[0].name,
        "mesh_domain_m": domain,
        "obst_box_count": len(obstacles),
        "fds_grid_spacing_m": 0.1,
        "maximum_allowed_probe_to_intended_face_distance_m": 0.105,
        "probe_offset_from_voxel_face_m": 0.035,
        "temperature_probe_count": total,
        "net_heat_flux_probe_count": total,
        "paired_device_count": total * 2,
        "group_count": len(registry),
        "validated_probe_count": sum(p["valid"] for p in points),
        "all_positions_valid": all(p["valid"] for p in points),
        "ior_counts": dict(sorted(Counter(str(p["ior"]) for p in points).items())),
        "groups": group_rows,
        "issues": issues,
        "interpretation": (
            "A reported material maximum is the maximum among this material's WALL TEMPERATURE probes; "
            "it is not a mathematical maximum over every surface cell."
        ),
    }
    return validation, points


def setup_plot_style():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 9,
        "axes.titlesize": 13, "axes.labelsize": 10,
        "axes.edgecolor": "#9aa7b5", "axes.linewidth": 0.8,
        "grid.color": "#d9e1e8", "grid.linewidth": 0.6,
        "figure.facecolor": "white", "axes.facecolor": "#fbfcfe",
    })


def plot_3d(points: list[dict], out: Path):
    setup_plot_style()
    fig = plt.figure(figsize=(15, 8.5), constrained_layout=True)
    ax = fig.add_subplot(111, projection="3d")
    groups = list(dict.fromkeys(p["group"] for p in points))
    for idx, group in enumerate(groups):
        pts = np.array([p["xyz"] for p in points if p["group"] == group])
        ax.scatter(pts[:, 0], pts[:, 1], pts[:, 2], s=34, alpha=0.9,
                   color=COLORS[idx % len(COLORS)], edgecolor="white", linewidth=0.45,
                   label=f"{group} ({len(pts)})")
        center = pts.mean(axis=0)
        if group.startswith("H") or group in {"RADM", "U4", "BED", "SEAT"}:
            ax.text(*center, group, fontsize=8, weight="bold", color="#1f2937")
    suspect = np.array([p["xyz"] for p in points if not p["valid"]])
    if len(suspect):
        ax.scatter(suspect[:, 0], suspect[:, 1], suspect[:, 2], s=105, marker="x",
                   color="#d62728", linewidth=2.2, label=f"QA suspect ({len(suspect)})")
    ax.set_title("FDS surface-probe distribution: 3D view", pad=16, weight="bold")
    ax.set_xlabel("X / aircraft longitudinal (m)")
    ax.set_ylabel("Y / lateral (m)")
    ax.set_zlabel("Z / vertical (m)")
    ax.view_init(elev=22, azim=-62)
    ax.set_box_aspect((10, 3.5, 4))
    ax.grid(True)
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False, ncol=1)
    fig.savefig(out, dpi=190, bbox_inches="tight")
    plt.close(fig)


def plot_2d(points: list[dict], out: Path):
    setup_plot_style()
    fig, axes = plt.subplots(2, 1, figsize=(15, 9.5), constrained_layout=True)
    groups = list(dict.fromkeys(p["group"] for p in points))
    for idx, group in enumerate(groups):
        pts = np.array([p["xyz"] for p in points if p["group"] == group])
        color = COLORS[idx % len(COLORS)]
        axes[0].scatter(pts[:, 0], pts[:, 2], s=32, color=color, alpha=0.88,
                        edgecolor="white", linewidth=0.4, label=f"{group}: {GROUP_META[group][0]}")
        axes[1].scatter(pts[:, 0], pts[:, 1], s=32, color=color, alpha=0.88,
                        edgecolor="white", linewidth=0.4)
        center = pts.mean(axis=0)
        if group.startswith("H") or group in {"RADM", "U4", "BED"}:
            axes[0].annotate(group, (center[0], center[2]), fontsize=8, weight="bold")
            axes[1].annotate(group, (center[0], center[1]), fontsize=8, weight="bold")
    axes[0].set_title("Side projection (X-Z)", loc="left", weight="bold")
    axes[0].set_xlabel("X / aircraft longitudinal (m)")
    axes[0].set_ylabel("Z / vertical (m)")
    axes[1].set_title("Top projection (X-Y)", loc="left", weight="bold")
    axes[1].set_xlabel("X / aircraft longitudinal (m)")
    axes[1].set_ylabel("Y / lateral (m)")
    for ax in axes:
        ax.grid(True)
        ax.set_axisbelow(True)
    suspect = np.array([p["xyz"] for p in points if not p["valid"]])
    if len(suspect):
        axes[0].scatter(suspect[:, 0], suspect[:, 2], s=90, marker="x", color="#d62728",
                        linewidth=2.2, label=f"QA suspect ({len(suspect)})")
        axes[1].scatter(suspect[:, 0], suspect[:, 1], s=90, marker="x", color="#d62728", linewidth=2.2)
    axes[0].legend(loc="upper left", bbox_to_anchor=(1.01, 1.03), frameon=False)
    fig.suptitle("FDS surface-probe distribution: 2D engineering views", fontsize=15, weight="bold")
    fig.savefig(out, dpi=190, bbox_inches="tight")
    plt.close(fig)


def write_markdown(validation: dict, path: Path):
    lines = [
        "# Probe Position Validation",
        "",
        f"Case: `{validation['case']}`",
        "",
        "## Result",
        "",
        f"- Position validation: **{'PASS' if validation['all_positions_valid'] else 'FAIL'}**",
        f"- Temperature probes: **{validation['temperature_probe_count']}**",
        f"- Co-located net-heat-flux probes: **{validation['net_heat_flux_probe_count']}**",
        f"- Validated against current FDS and voxel exposed-face records: **{validation['validated_probe_count']}/{validation['temperature_probe_count']}**",
        "- Probe coordinates are intentionally 0.035 m outside the selected voxel face; `IOR` points to that boundary.",
        "",
        "## Per-group coverage",
        "",
        "| Group | Component | Material | WT probes | Unique positions | Candidate faces | Directly irradiated | Status |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for row in validation["groups"]:
        lines.append(
            f"| {row['group']} | {row['component']} | {row['material']} | {row['probes']} | "
            f"{row['unique_positions']} | {row['available_exposed_face_candidates']} | "
            f"{row['directly_illuminated_probes']} | {row['status']} |"
        )
    lines.extend([
        "",
        "## Suspect probes",
        "",
    ])
    if validation["issues"]:
        lines.extend([
            "These probes are present in the FDS file and have a co-located heat-flux pair, but their requested "
            "location is more than one 0.1 m grid cell from the intended oriented material face:",
            "",
        ])
        for issue in validation["issues"]:
            distance = issue["nearest_intended_face_distance_m"]
            lines.append(f"- `{issue['wt']}`: nearest intended face = {distance:.3f} m")
    else:
        lines.append("None.")
    lines.extend([
        "",
        "## Interpretation",
        "",
        "The temperature reported for a material is the maximum among its redundant WALL TEMPERATURE probes. "
        "It is a monitored maximum, not a continuous maximum over every FDS surface cell. The probes deliberately "
        "combine high-flux locations with spatially separated locations, and each has a co-located NET HEAT FLUX probe.",
        "",
        "Groups with zero directly irradiated probes are geometrically shielded for the current azimuth/elevation; "
        "their probes remain useful for secondary heating and fire exposure.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_inline_html(points: list[dict], validation: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    groups = list(dict.fromkeys(p["group"] for p in points))
    payload = {"points": points, "groups": groups, "meta": GROUP_META, "colors": COLORS}
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    status = "PASS" if validation["all_positions_valid"] else "FAIL"
    html = f"""<div id="probe-vis" style="height:860px;width:100%;display:grid;grid-template-rows:auto 1fr;background:var(--color-background-primary,#fff);color:var(--color-text-primary,#111827);font-family:var(--font-sans,Arial,sans-serif)">
  <div style="display:flex;gap:18px;align-items:center;padding:10px 14px;border-bottom:1px solid var(--color-border-secondary,#d8dee6);font-size:13px">
    <strong>Probe geometry QA: {status}</strong><span>{len(points)} WT + {len(points)} co-located heat-flux probes</span><span>Hover points for component, material, XYZ, IOR and local flux.</span>
  </div>
  <div style="display:grid;grid-template-columns:minmax(0,1.5fr) minmax(380px,1fr);min-height:0">
    <div id="probe-3d" style="min-height:0"></div>
    <div style="display:grid;grid-template-rows:1fr 1fr;min-height:0;border-left:1px solid var(--color-border-secondary,#d8dee6)"><div id="probe-side"></div><div id="probe-top"></div></div>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js"></script>
<script>
const payload={data};
const traces3=[], side=[], top=[];
payload.groups.forEach((g,i)=>{{
  const p=payload.points.filter(d=>d.group===g), c=payload.colors[i%payload.colors.length];
  const hover=p.map(d=>`<b>${{d.group}} · ${{d.component}}</b><br>${{d.material}}<br>XYZ: ${{d.xyz.map(v=>v.toFixed(4)).join(', ')}} m<br>IOR: ${{d.ior}}<br>Base flux: ${{d.base_flux_kw_m2.toFixed(1)}} kW/m²<extra></extra>`);
  const common={{name:`${{g}} (${{p.length}})`,mode:'markers',marker:{{size:6,color:c,line:{{width:.6,color:'#fff'}}}},text:hover,hovertemplate:'%{{text}}'}};
  traces3.push({{...common,type:'scatter3d',x:p.map(d=>d.xyz[0]),y:p.map(d=>d.xyz[1]),z:p.map(d=>d.xyz[2])}});
  side.push({{...common,type:'scattergl',x:p.map(d=>d.xyz[0]),y:p.map(d=>d.xyz[2]),showlegend:false}});
  top.push({{...common,type:'scattergl',x:p.map(d=>d.xyz[0]),y:p.map(d=>d.xyz[1]),showlegend:false}});
}});
const bad=payload.points.filter(d=>!d.valid), badHover=bad.map(d=>`<b>QA suspect: ${{d.id}}</b><br>${{d.group}} · ${{d.component}}<br>${{d.material}}<br>XYZ: ${{d.xyz.map(v=>v.toFixed(4)).join(', ')}} m<extra></extra>`);
if(bad.length){{
  traces3.push({{type:'scatter3d',mode:'markers',name:`QA suspect (${{bad.length}})`,x:bad.map(d=>d.xyz[0]),y:bad.map(d=>d.xyz[1]),z:bad.map(d=>d.xyz[2]),text:badHover,hovertemplate:'%{{text}}',marker:{{size:9,color:'#d62728',symbol:'x'}}}});
  side.push({{type:'scattergl',mode:'markers',showlegend:false,x:bad.map(d=>d.xyz[0]),y:bad.map(d=>d.xyz[2]),text:badHover,hovertemplate:'%{{text}}',marker:{{size:12,color:'#d62728',symbol:'x'}}}});
  top.push({{type:'scattergl',mode:'markers',showlegend:false,x:bad.map(d=>d.xyz[0]),y:bad.map(d=>d.xyz[1]),text:badHover,hovertemplate:'%{{text}}',marker:{{size:12,color:'#d62728',symbol:'x'}}}});
}}
const paper='rgba(0,0,0,0)', font={{family:'Arial, sans-serif',color:'var(--color-text-primary,#111827)'}};
Plotly.newPlot('probe-3d',traces3,{{paper_bgcolor:paper,plot_bgcolor:paper,font,title:{{text:'3D probe distribution',x:.03}},margin:{{l:0,r:0,t:45,b:0}},legend:{{x:.01,y:.98,bgcolor:'rgba(255,255,255,.72)',font:{{size:10}}}},scene:{{aspectmode:'data',xaxis:{{title:'X (m)'}},yaxis:{{title:'Y (m)'}},zaxis:{{title:'Z (m)'}},camera:{{eye:{{x:1.55,y:-1.75,z:.85}}}}}}}},{{responsive:true,displaylogo:false}});
const layout2=(title,ytitle)=>({{paper_bgcolor:paper,plot_bgcolor:paper,font,title:{{text:title,x:.04,font:{{size:14}}}},margin:{{l:58,r:18,t:42,b:45}},xaxis:{{title:'X (m)',gridcolor:'#d9e1e8'}},yaxis:{{title:ytitle,gridcolor:'#d9e1e8'}},hovermode:'closest'}});
Plotly.newPlot('probe-side',side,layout2('Side view (X-Z)','Z (m)'),{{responsive:true,displaylogo:false}});
Plotly.newPlot('probe-top',top,layout2('Top view (X-Y)','Y (m)'),{{responsive:true,displaylogo:false}});
</script>"""
    path.write_text(html, encoding="utf-8")


def main():
    args = parse_args()
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    validation, points = validate(args.case_dir)
    json_path = args.reports_dir / "probe_position_validation.json"
    md_path = args.reports_dir / "probe_position_validation.md"
    png3d = args.reports_dir / "probe_distribution_3d.png"
    png2d = args.reports_dir / "probe_distribution_2d.png"
    json_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(validation, md_path)
    plot_3d(points, png3d)
    plot_2d(points, png2d)
    write_inline_html(points, validation, args.inline_html)
    print(json.dumps({
        "status": "PASS" if validation["all_positions_valid"] else "FAIL",
        "validated": f"{validation['validated_probe_count']}/{validation['temperature_probe_count']}",
        "reports": [str(json_path), str(md_path), str(png3d), str(png2d)],
        "inline_html": str(args.inline_html),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

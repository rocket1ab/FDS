#!/usr/bin/env python3
"""Build coarse-grid and fixed-Q yield-independence cases without touching baselines."""
from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_SUFFIX = "H1H7_v5_Qnorm_adapt_HRRupper_thickness_audit"
GRID_Q = (50, 200, 100, 400)
YIELDS_KT = (10, 50, 200, 500, 1000)


def blocks(text: str, name: str) -> list[str]:
    return re.findall(rf"&{name}\b[\s\S]*?/", text, flags=re.I)


def trapz(points: list[tuple[float, float]]) -> float:
    return sum((f0 + f1) * (t1 - t0) / 2 for (t0, f0), (t1, f1) in zip(points, points[1:]))


def copy_case(source_name: str, output_dir: Path, case_name: str) -> tuple[Path, dict]:
    source = ROOT / "cases_adaptive" / source_name
    if not source.is_dir():
        raise FileNotFoundError(source)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    for name in (f"{source_name}.fds", "monitor_registry.json", "flux_faces.csv", "case_summary.json"):
        shutil.copy2(source / name, output_dir / name)
    old_fds = output_dir / f"{source_name}.fds"
    new_fds = output_dir / f"{case_name}.fds"
    old_fds.replace(new_fds)
    summary = json.loads((output_dir / "case_summary.json").read_text(encoding="utf-8"))
    return new_fds, summary


def set_chid(text: str, case_name: str) -> str:
    text, count = re.subn(
        r"(&HEAD\b[^/]*CHID\s*=\s*')[^']+(')", rf"\g<1>{case_name}\g<2>",
        text, count=1, flags=re.I,
    )
    if count != 1:
        raise RuntimeError("HEAD/CHID replacement failed")
    return text


def coarsen_meshes(text: str, mpi: int = 20) -> tuple[str, list[dict]]:
    mesh_index = 0
    records: list[dict] = []

    def edit(match: re.Match[str]) -> str:
        nonlocal mesh_index
        block = match.group(0)
        ijk_match = re.search(r"IJK\s*=\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", block, flags=re.I)
        xb_match = re.search(r"XB\s*=\s*([-+\d.Ee]+)\s*,\s*([-+\d.Ee]+)\s*,\s*([-+\d.Ee]+)\s*,\s*([-+\d.Ee]+)\s*,\s*([-+\d.Ee]+)\s*,\s*([-+\d.Ee]+)", block, flags=re.I)
        if not ijk_match or not xb_match:
            raise RuntimeError(f"Invalid MESH: {block[:120]}")
        old = tuple(map(int, ijk_match.groups()))
        new = tuple(max(1, math.ceil(value / 2)) for value in old)
        bounds = tuple(map(float, xb_match.groups()))
        old_d = tuple((bounds[2*i+1] - bounds[2*i]) / old[i] for i in range(3))
        new_d = tuple((bounds[2*i+1] - bounds[2*i]) / new[i] for i in range(3))
        process = mesh_index * mpi // 32
        mesh_index += 1
        block = re.sub(r"IJK\s*=\s*\d+\s*,\s*\d+\s*,\s*\d+", f"IJK={new[0]},{new[1]},{new[2]}", block, count=1, flags=re.I)
        block = re.sub(r"MPI_PROCESS\s*=\s*\d+", f"MPI_PROCESS={process}", block, count=1, flags=re.I)
        records.append({"old_ijk": old, "new_ijk": new, "old_cell_m": old_d, "new_cell_m": new_d, "mpi_process": process})
        return block

    result = re.sub(r"&MESH\b[\s\S]*?/", edit, text, flags=re.I)
    if len(records) != 32:
        raise RuntimeError(f"Expected 32 MESH records, found {len(records)}")
    return result, records


def build_grid(q: int) -> str:
    source_name = f"Q{q:04d}_W0100_az270_el15_{BASE_SUFFIX}"
    case_name = f"Q{q:04d}_W0100_grid_coarse"
    output = ROOT / "cases_verification" / "grid_coarse" / case_name
    fds, summary = copy_case(source_name, output, case_name)
    text = set_chid(fds.read_text(encoding="utf-8", errors="replace"), case_name)
    text, mesh_records = coarsen_meshes(text)
    note = (
        "! Grid-resolution verification: approximately 2x coarser cell spacing.\n"
        "! Domain, geometry, external-flux field, materials, probes and criteria unchanged.\n"
    )
    fds.write_text(note + text, encoding="utf-8")
    old_cells = sum(math.prod(item["old_ijk"]) for item in mesh_records)
    new_cells = sum(math.prod(item["new_ijk"]) for item in mesh_records)
    summary.update(
        case=case_name, purpose="grid_resolution_coarse_verification", source_case=source_name,
        changed_factor="MESH_IJK_only", grid_level="coarse_approximately_2x_spacing",
        old_total_cells=old_cells, new_total_cells=new_cells,
        cell_count_ratio=new_cells / old_cells, mesh_records=mesh_records, mpi=20,
        geometry_changed=False, external_flux_changed=False, materials_changed=False,
        probes_changed=False, damage_thresholds_changed=False,
    )
    (output / "case_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return case_name


def parse_ramp(text: str) -> list[tuple[float, float]]:
    return [(float(t), float(f)) for t, f in re.findall(
        r"&RAMP\s+ID='NUCLEAR_RAMP',\s*T=([-+\d.Ee]+),\s*F=([-+\d.Ee]+)", text, flags=re.I)]


def build_yield(yield_kt: int) -> str:
    source_name = f"Q0050_W0100_az270_el15_{BASE_SUFFIX}"
    case_name = f"Q0050_W{yield_kt:04d}_yield_independence"
    output = ROOT / "cases_verification" / "yield_Q50" / case_name
    fds, summary = copy_case(source_name, output, case_name)
    text = set_chid(fds.read_text(encoding="utf-8", errors="replace"), case_name)
    old_ramp = parse_ramp(text)
    old_peak_t = max(old_ramp, key=lambda pair: pair[1])[0]
    target_peak_t = 0.044 * yield_kt ** 0.42
    time_scale = target_peak_t / old_peak_t
    peak_scale = 1.0 / time_scale
    new_ramp = [(t * time_scale, f) for t, f in old_ramp]
    ramp_lines = "\n".join(f"&RAMP ID='NUCLEAR_RAMP', T={t:.6f}, F={f:.6f} /" for t, f in new_ramp)
    text, ramp_count = re.subn(r"(?:&RAMP\s+ID='NUCLEAR_RAMP',[^\n]*\n?)+", ramp_lines + "\n", text, count=1, flags=re.I)
    flux_count = 0

    def scale_flux(match: re.Match[str]) -> str:
        nonlocal flux_count
        flux_count += 1
        return match.group(1) + f"{float(match.group(2)) * peak_scale:.6f}"

    text = re.sub(r"(EXTERNAL_FLUX\s*=\s*)([-+\d.Ee]+)", scale_flux, text, flags=re.I)
    if ramp_count != 1 or flux_count == 0:
        raise RuntimeError(f"Yield replacement failed: ramp={ramp_count}, flux={flux_count}")
    note = (
        f"! Yield-independence verification at fixed Q=50 J/cm2: W={yield_kt} kt.\n"
        "! Only NUCLEAR_RAMP time scale and reciprocal EXTERNAL_FLUX peak scale changed.\n"
    )
    fds.write_text(note + text, encoding="utf-8")
    summary.update(
        case=case_name, purpose="yield_independence_at_fixed_Q50", source_case=source_name,
        changed_factor="yield_pulse_duration_at_fixed_incident_plane_fluence",
        Q_J_cm2=50, yield_kt=yield_kt, t_max_s=target_peak_t,
        ramp_integral_s=trapz(new_ramp), time_scale_vs_W100=time_scale,
        external_flux_peak_scale_vs_W100=peak_scale, scaled_external_flux_records=flux_count,
        mpi=20, geometry_changed=False, grid_changed=False, materials_changed=False,
        probes_changed=False, damage_thresholds_changed=False,
        fixed_Q_normalization=True,
    )
    (output / "case_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return case_name


def write_report(grid_cases: list[str], yield_cases: list[str]) -> None:
    report = ROOT / "reports" / "grid_and_yield_independence_verification.md"
    lines = [
        "# 网格分辨率与核爆当量独立性验证", "",
        "## 1. 验证目标", "",
        "本验证使用当前 HRRPUA 上限值与审查后厚度方案。所有验证案例均为新建副本，不覆盖基线输入和结果。", "",
        "## 2. 网格分辨率验证方法", "",
        "粗网格保持计算域、几何、DDA 外部热流、材料、探针和毁伤判据不变，仅将每个 MESH 的各方向单元数约减半，格距约扩大为原来的 2 倍。", "",
        "比较指标包括：17组毁伤等级、整机毁伤树等级、各组峰值温度与阈值持续时间、全域 HRR 峰值及积分、点火顺序。建议一致性门槛为关键峰值相对差不超过10%，毁伤等级与关键系统结论不改变。", "",
        "| 顺序 | 粗网格案例 | 状态 | 与现网格对比 |", "|---:|---|---|---|",
    ]
    lines += [f"| {i} | `{case}` | 待运行 | 待计算 |" for i, case in enumerate(grid_cases, 1)]
    lines += ["", "## 3. 固定 Q=50 J/cm² 的当量验证方法", "",
              "采用 t_max=0.044 W^0.42 s 缩放 NUCLEAR_RAMP 时间轴，并按时间缩放系数的倒数缩放 EXTERNAL_FLUX 峰值，保证积分光冲量保持 Q=50 J/cm²。", "",
              "| 顺序 | 当量（kt） | 案例 | 状态 |", "|---:|---:|---|---|"]
    lines += [f"| {i} | {w} | `{case}` | 待运行 |" for i, (w, case) in enumerate(zip(YIELDS_KT, yield_cases), 1)]
    lines += ["", "## 4. 结果更新规则", "",
              "每个案例正常完成1500 s后运行统一毁伤评估，并更新温度、HRR/HRRPUA、毁伤树和逐设备状态。异常停止但有效时间达到1000 s的结果仅标记为长时快照。", ""]
    report.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    grid_cases = [build_grid(q) for q in GRID_Q]
    yield_cases = [build_yield(w) for w in YIELDS_KT]
    write_report(grid_cases, yield_cases)
    manifest = {"grid_cases_in_order": grid_cases, "yield_cases_in_order": yield_cases}
    path = ROOT / "cases_verification" / "verification_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

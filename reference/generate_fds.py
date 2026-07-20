#!/usr/bin/env python3
"""
generate_fds.py — 厂房核爆平行光 → FDS 工况生成器

用法:
  python generate_fds.py --model zhizao --label G_az270_el45 --E0 1287 --az 270 --el 45
  python generate_fds.py --model zongzhuang --all
"""
import re
import json
import argparse
import shutil
from pathlib import Path

import factory_flux_voxel as V
import damage_criteria as DC
from factory_model_config import get_model, SCENARIOS, T_END
from scenario_paths import chid_for_tag, scenario_dir
from mpi_split import split_mesh_for_mpi


IOR_MAP = {'-x': -1, '+x': 1, '-y': -2, '+y': 2, '-z': -3, '+z': 3}


def _tag_for(label, az, el):
    has_az = '_az' in label
    has_el = '_el' in label
    if has_az and has_el:
        return label
    if has_el and not has_az:
        return re.sub(r'_el(\d+)', lambda m: f'_az{int(az):03d}_el{m.group(1)}', label)
    if has_az and not has_el:
        return f'{label}_el{int(round(el)):02d}'
    return f'{label}_az{int(az):03d}_el{int(round(el)):02d}'


def build_damage_monitors(obsts, comb_merged, cfg):
    """Place WALL TEMPERATURE probes on combustible OBST."""
    by_obst = {}
    for r in comb_merged:
        oid = r['obst_id']
        if oid not in by_obst or r['q'] > by_obst[oid]['q']:
            by_obst[oid] = r

    # Fallback: monitor all combustible OBST even if no direct flux (shadow)
    for ob in obsts:
        if ob['comb'] and ob['idx'] not in by_obst:
            by_obst[ob['idx']] = dict(
                obst_id=ob['idx'], q=0.0, axis=0, sign=1, surf=ob['surf'])

    lines = ["\n! ══ 设备毁伤监测探针（双重判据 DEVC）══"]
    monitor_map = {}
    idx = 0
    for oid, r in sorted(by_obst.items()):
        ob = obsts[oid]
        mat = ob['surf']
        lookup = DC.lookup_by_matl(mat)
        if not lookup:
            continue
        _, crit_key, crit = lookup
        xb = ob['xb']
        ax, sign = r.get('axis', 2), r.get('sign', 1)
        ior = (ax + 1) * (1 if sign > 0 else -1)
        cx = (xb[0]+xb[1])/2; cy = (xb[2]+xb[3])/2; cz = (xb[4]+xb[5])/2
        eps = 0.05
        # Top face (+Z) default for flat combustible pallets
        pt = [cx, cy, xb[5] + eps]
        ior = 3
        did = f"D_{idx}_{crit.get('abbr','X')}"
        lines.append(f"&DEVC ID='{did}_WT', QUANTITY='WALL TEMPERATURE', "
                     f"XYZ={pt[0]:.3f},{pt[1]:.3f},{pt[2]:.3f}, IOR={ior}/")
        lines.append(f"&DEVC ID='{did}_HF', QUANTITY='NET HEAT FLUX', "
                     f"XYZ={pt[0]:.3f},{pt[1]:.3f},{pt[2]:.3f}, IOR={ior}/")
        monitor_map[f'{did}_WT'] = dict(
            material=mat, crit_key=crit_key,
            T_crit=crit['T_crit'], tau_tol=crit['tau_tol'],
            flux=round(r['q'], 1), xyz=[round(v, 3) for v in pt], ior=ior,
            part_label=DC.part_label_for_matl(mat),
        )
        idx += 1

    for i, (x, y, z) in enumerate(cfg.get('gas_probes', [])):
        lines.append(f"&DEVC ID='GAS_{i}', QUANTITY='TEMPERATURE', "
                     f"XYZ={x:.2f},{y:.2f},{z:.2f}/")

    sl = cfg.get('slcf', {})
    lines.append(f"&SLCF PBY={sl.get('pby', 15)}, QUANTITY='TEMPERATURE'/")
    lines.append(f"&SLCF PBZ={sl.get('pbz', 8)}, QUANTITY='TEMPERATURE'/")
    lines.append(f"&SLCF PBX={sl.get('pbx', 0)}, QUANTITY='TEMPERATURE'/")
    lines.append("&BNDF QUANTITY='WALL TEMPERATURE'/")
    lines.append("&BNDF QUANTITY='NET HEAT FLUX'/")
    return lines, monitor_map


def generate_one(model_key, fds_path, E0, az, el, label, out_dir, ncores=16):
    cfg = get_model(model_key)
    tag = _tag_for(label, az, el)
    chid = chid_for_tag(tag)
    scen_dir = scenario_dir(out_dir, tag)
    scen_dir.mkdir(parents=True, exist_ok=True)

    print(f'\n{"─"*64}')
    print(f'  [{cfg["name"]}] 工况 {tag}: E0={E0} az={az} el={el}')

    raw = Path(fds_path).read_text(encoding='utf-8', errors='ignore')
    txt = V.preprocess_fds(raw, cfg)
    obsts = V.parse_obsts(txt, cfg)
    domain = V.domain_from_meshes(txt, obsts)
    u = V.sun_vec(az, el)

    print(f'  OBST={len(obsts)} (doors removed, burners stripped)')
    result = V.compute_all_flux(obsts, domain, u, E0, cfg)

    all_merged = result['env_merged'] + result['comb_merged']
    surf_lines, vent_lines = V.build_vent_lines(all_merged, cfg)

    mon_lines, mon_map = build_damage_monitors(obsts, result['comb_merged'], cfg)

    # T_END
    if re.search(r'&TIME[^/]*T_END\s*=', txt):
        txt = re.sub(r'(&TIME[^/]*?T_END\s*=\s*)[\d.eE+-]+', rf'\g<1>{T_END}', txt, count=1)
    else:
        txt = re.sub(r'(&HEAD[^/]*/)', rf'\1\n&TIME T_END={T_END}/', txt, count=1)

    txt = re.sub(r"(&HEAD[^/]*CHID=')[^']+(')", rf"\g<1>{chid}\g<2>", txt, count=1)

    inject_head = (
        f"\n! ===== 核爆平行光注入（门全开，无 Burner）tag={tag} =====\n"
        f"{V.ramp_block()}\n\n"
        + '\n'.join(surf_lines) + '\n'
    )
    mpos = txt.find('&MATL')
    if mpos >= 0:
        txt = txt[:mpos] + inject_head + txt[mpos:]
    else:
        txt = inject_head + txt

    tail = (
        f"\n! ===== 受照面 EXTERNAL_FLUX VENT ({len(vent_lines)} 个) =====\n"
        + '\n'.join(vent_lines) + '\n'
        + '\n'.join(mon_lines) + '\n'
    )
    if '&TAIL' in txt:
        txt = txt.replace('&TAIL', tail + '\n&TAIL', 1)
    else:
        txt += tail + '\n&TAIL/\n'

    txt, n_mpi = split_mesh_for_mpi(txt, ncores)
    if n_mpi:
        print(f'  MPI split: {n_mpi} blocks (mpiexec -n {n_mpi})')

    out_fds = scen_dir / f'{chid}.fds'
    out_fds.write_text(txt, encoding='utf-8')

    map_path = scen_dir / f'monitor_map_{tag}.json'
    map_path.write_text(json.dumps(mon_map, ensure_ascii=False, indent=2), encoding='utf-8')

    V.write_flux_csv(result['env_recs'] + result['comb_recs'],
                     scen_dir / f'flux_{tag}.csv')
    summary = V.write_summary(tag, E0, az, el, result, scen_dir)
    summary['n_monitors'] = len(mon_map)
    summary['chid'] = chid

    flat = Path(out_dir) / f'{chid}.fds'
    if flat != out_fds:
        shutil.copy2(out_fds, flat)
        shutil.copy2(map_path, Path(out_dir) / f'monitor_map_{tag}.json')

    print(f'  → {out_fds}  vents={len(vent_lines)}  monitors={len(mon_map)}')
    return summary


def main():
    ap = argparse.ArgumentParser(description='厂房平行光 FDS 生成器')
    ap.add_argument('--model', required=True, choices=['zhizao', 'zongzhuang'])
    ap.add_argument('--fds', help='输入 FDS（默认取模型 fds/ 下源文件）')
    ap.add_argument('--out', default=None, help='输出目录（默认 ../{model}/fds）')
    ap.add_argument('--label', default='G_az270_el45')
    ap.add_argument('--E0', type=float, default=1287.)
    ap.add_argument('--az', type=float, default=270.)
    ap.add_argument('--el', type=float, default=45.)
    ap.add_argument('--all', action='store_true', help='生成全部 17 工况')
    ap.add_argument('--ncores', type=int, default=None)
    args = ap.parse_args()

    cfg = get_model(args.model)
    fds = args.fds or str(cfg['fds_source'])
    out = args.out or str(cfg['root'] / 'fds')
    ncores = args.ncores or cfg['ncores_default']

    print('='*64)
    print(f'  厂房平行光毁伤 FDS 生成 — {cfg["name"]}')
    print(f'  源: {fds}')
    print('='*64)

    if args.all:
        for label, E0, az, el in SCENARIOS:
            generate_one(args.model, fds, E0, az, el, label, out, ncores)
    else:
        generate_one(args.model, fds, args.E0, args.az, args.el, args.label, out, ncores)


if __name__ == '__main__':
    main()

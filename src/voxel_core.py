#!/usr/bin/env python3
"""
nuclear_flux_voxel.py
=====================
核爆光辐射平行光 → B-52H 舱段 FDS 火灾仿真：逐体素热流赋值主程序

功能流程
--------
  ① 解析 PyroSim 生成的 FDS 文件（jitou_20260609_v5.fds）
  ② 构建非可燃 OBST 的三维体素遮挡网格
  ③ 对每个可燃薄板 OBST 的受照面进行 DDA 射线追踪 → 可见率
  ④ 大面板自动分割为子片（per-patch），相同热流子片合并
  ⑤ 生成 SURF 辐射变体（EXTERNAL_FLUX × RAMP_EF='NUCLEAR_RAMP'）
     —— 可燃面 + 铝合金外露面（AL_FLUX_MAP；铝同时仍作遮挡）
  ⑥ 注入 DEVC 测点（壁温/净热流/气温/O2/CO/能见度）+ SLCF 观测平面 + BNDF
  ⑦ 输出新 FDS 文件 + 热流分布图（PNG）+ 热流数据（CSV）

用法
----
    python nuclear_flux_voxel.py                                    # 默认工况
    python nuclear_flux_voxel.py --E0 1287 --az 270 --el 26.57      # 指定工况
    python nuclear_flux_voxel.py --fds my_model.fds --out ./results # 指定文件
    python nuclear_flux_voxel.py --all-scenarios                    # 批量 10 工况
"""

import re, argparse, time, json
import csv
import numpy as np
from pathlib import Path
from collections import Counter, defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

# This module is retained as the audited geometric kernel. Plot styling and
# damage criteria live in the new project and are intentionally decoupled.

# 材料缩写 → 中文（体素法 CSV / 图内图例）
MAT_ABBR_ZH = {
    'EGFR': 'E-玻璃纤维(雷达罩)', 'ACRY': '丙烯酸塑料(风挡)',
    'FOAM': '聚氨酯泡沫(座椅)', 'NCUR': '尼龙窗帘', 'NBED': '尼龙床垫',
    'GFRP': '环氧玻璃纤维(仪表台)',
    'AL24': '铝合金2024(蒙皮)', 'AL52': '铝合金5052(通风管)',
    'AL75': '铝合金7075(隔框)', 'ALO2': '铝合金7075(氧气瓶)',
    'H1': '导航子系统', 'H2': '任务子系统', 'H3': '显示子系统',
    'H4': '通信子系统', 'H5': '电池', 'H6': '电力传输子系统',
    'H7': '操纵子系统',
}

# ══════════════════════════════════════════════════════════════════════════════
# §1  全局常量
# ══════════════════════════════════════════════════════════════════════════════
# v5 模型网格：204×72×96，格距 0.05m
GRID_CELL  = 0.05      # m   FDS 网格格距（参考值）
DDA_PITCH  = 0.05      # m   DDA 遮挡体素网格默认格距（可被 --pitch 覆盖）
# ── 关于混合分辨率网格 ──
# 体素法的遮挡网格是【独立于 FDS 网格的统一立方体素网格】，专为射线追踪服务，
# 不直接使用 FDS 的网格。因此 FDS 用几套不同分辨率的 MESH 都不影响体素法的工作
# 方式——体素法只按自己的 pitch 把所有 OBST 几何体素化。
# 对本模型(MESH01=0.1m + MESH02≈0.0556/0.05m)：
#   - MESH01 区(0.1m)：0.1=2×0.05，OBST 坐标在 0.05m 体素网格上完全对齐，无误差；
#   - MESH02 区(dx≈0.0556m)：与 0.05m 体素有 ~2.8mm 的离散吸附偏差(<1%)，可忽略；
#   - 若要消除该偏差，可用 --pitch 0.025（更细，体素数×8，内存~55MB）。
PATCH_RES  = 0.10      # m   大面板分割子片尺寸（=2×网格格距）
SPLIT_MIN  = 0.15      # m   面边长超过该值才做 per-patch 分割
FLUX_STEP  = 50.0      # kW/m²  热流量化步长（控制 SURF 变体数量）
N_SAMPLE   = 2         # 每个子片 2×2=4 点采样

# 可燃 SURF（中文名 → 简称缩写，用于 SURF 变体命名）
# 注意：本模型(Jitou_with_fengxi)的材料名与 v5 略有差异——
#   窗帘为"3mmm"(三个m)、床垫无空格。这里按本模型实际名称配置。
COMB_MAP = {
    '聚氨酯泡沫':       'FOAM',
    '丙烯酸塑料':       'ACRY',
    '尼龙织物_床垫':    'NBED',   # 本模型无空格
    '尼龙织物_窗帘3mm': 'NCUR',   # 本模型双 m（与 fengxi 的三 m 不同）
    '尼龙织物_窗帘3mmm': 'NCUR',  # Separated_merge_v2 三 m 变体
    '环氧玻璃纤维':     'GFRP',
    'E-玻璃纤维':       'EGFR',   # 本模型新增材料（机头段结构件，X[0,1.4]）
}
COMB_SURFS  = set(COMB_MAP.keys())
GLASS_SURFS = {'丙烯酸塑料'}      # 半透明材料（舷窗玻璃，位于座舱 X[1.7,4.3] Z[1.1,1.8]）
GLASS_TRANS = 0.85                # 玻璃单层透射率

# 非可燃（遮挡）SURF
EQUIPMENT_SURFS = {
    '导航子系统', '任务子系统', '显示子系统', '通信子系统',
    '电池', '电力传输子系统', '操纵子系统',
}
OPAQUE_SURFS = {
    '铝合金2024', '铝合金5052', '铝合金7075', '铝合金7075_氧气瓶',
    '铝合金6061', *EQUIPMENT_SURFS,
}

# 铝合金也接收核脉冲 EXTERNAL_FLUX（仍作遮挡体；与可燃面同样生成 AL*_R#### 变体）
# 既往版本只给 COMB_SURFS 赋通量，导致蒙皮几乎不升温——后续版本必须包含下列材料。
AL_FLUX_MAP = {
    '铝合金2024': 'AL24',           # 蒙皮
    '铝合金5052': 'AL52',           # 通风管
    '铝合金7075': 'AL75',           # 隔框/隔板
    '铝合金7075_氧气瓶': 'ALO2',
    '铝合金6061': 'AL61',
    '导航子系统': 'H1',
    '任务子系统': 'H2',
    '显示子系统': 'H3',
    '通信子系统': 'H4',
    '电池': 'H5',
    '电力传输子系统': 'H6',
    '操纵子系统': 'H7',
}
AL_FLUX_SURFS = set(AL_FLUX_MAP.keys())
# 所有需要写 EXTERNAL_FLUX 的 SURF（可燃 + 铝合金）
FLUX_RECV_MAP = {**COMB_MAP, **AL_FLUX_MAP}
FLUX_RECV_SURFS = set(FLUX_RECV_MAP.keys())

FN = {'-x': np.array([-1., 0, 0]), '+x': np.array([1., 0, 0]),
      '-y': np.array([0, -1., 0]), '+y': np.array([0, 1., 0]),
      '-z': np.array([0, 0, -1.]), '+z': np.array([0, 0, 1.])}

# 预设核爆工况（标签, E0 kW/m², az °, el °）
SCENARIOS = [
    ('E1_1kt',    895.,  90., 26.57),
    ('E1_1kt',    895., 270., 26.57),
    ('E2_20kt',  1007.,  90., 26.57),
    ('E2_20kt',  1007., 270., 26.57),
    ('E3_100kt', 1287.,  90., 26.57),
    ('E3_100kt', 1287., 270., 26.57),
    ('E3_100kt', 1287.,  90., 45.0),
    ('E3_100kt', 1287.,  90.,  5.0),
    ('E4_1000kt', 951.,  90., 26.57),
    ('E4_1000kt', 951., 270., 26.57),
]


def sun_vec(az, el):
    """太阳方向单位矢量（从场景指向爆点）。az: 方位角（北=0,东=90），el: 仰角"""
    a, e = np.radians(az), np.radians(el)
    return np.array([np.sin(a)*np.cos(e), np.cos(a)*np.cos(e), np.sin(e)])


# ══════════════════════════════════════════════════════════════════════════════
# §2  FDS 文件解析
# ══════════════════════════════════════════════════════════════════════════════
def strip_external_flux(surf_raw):
    """剥离 SURF 块中的 EXTERNAL_FLUX 和 RAMP_EF 参数（PyroSim 预设的全局加热）。"""
    s = re.sub(r",?\s*EXTERNAL_FLUX\s*=\s*[\d.E+-]+", '', surf_raw)
    s = re.sub(r",?\s*RAMP_EF\s*=\s*'[^']*'", '', s)
    # 清理可能残留的 ",,"、",/"
    s = re.sub(r',\s*,', ',', s)
    s = re.sub(r',\s*/', '/', s)
    return s


# 写 FDS 时是否为受照可燃 OBST 注入 BULK_DENSITY（配合 SURF BURN_AWAY）
_BURN_AWAY_OBST_MODE = False


def set_burn_away_obst_mode(enabled=True):
    global _BURN_AWAY_OBST_MODE
    _BURN_AWAY_OBST_MODE = bool(enabled)


def parse_fds(path, chemistry_mode='unified', thickness_scale=None,
              param_profile=None, keep_burn_away=False, seal_enclosure=False,
              patch_gaps=False):
    """
    解析 FDS 文件 → (full_text, blocks, obs)
      blocks : 按类型分组的非 OBST 块（保留原文）
      obs    : OBST 列表 [{xb, surf, raw, comb, idx}]
    注意：可燃 SURF 中 PyroSim 预设的 EXTERNAL_FLUX=1000 会被剥离
         （改为由逐体素方法精确赋值）。

    chemistry_mode : 'unified' | 'multireac' | 'multidamage' | 'validated_ae'
                     | 'bst_burn' | 'user_20260620' | 'user_20260620_multireac'
    thickness_scale: None 或浮点倍数；对可燃 SURF 的 THICKNESS(1) 缩放（thickmatl 变体）
    param_profile  : None | 'low_hor' | 'reac20' | 'thin_bed' | 'ignite' | 'litreview'
                     文献核对表参数修正（见 fds_material_variants.PARAM_VARIANTS）
    keep_burn_away : True 时在 base SURF 写入 BURN_AWAY 且不剥离（需 BULK_DENSITY）
    seal_enclosure : True 时移除 MESH 顶面 ZMAX OPEN 边界（密闭舱）
    patch_gaps     : True 时机头/机尾/顶部补封闭 OBST
    """
    import fds_material_variants as FMV

    set_burn_away_obst_mode(keep_burn_away)
    txt = Path(path).read_text(encoding='utf-8', errors='ignore')
    bst_mode = chemistry_mode == 'bst_burn'

    # ── 剥离 base SURF 的预设 EXTERNAL_FLUX（关键！）────────────────────
    for m in list(re.finditer(r"&SURF[\s\S]*?/", txt)):
        raw = m.group()
        if 'EXTERNAL_FLUX' in raw:
            cleaned = strip_external_flux(raw)
            txt = txt.replace(raw, cleaned, 1)

    # ── 可燃 MATL 热解链 + 气相 REAC（unified / multireac）──────────────
    txt, n_matl_fix, chem_tag = FMV.apply_chemistry(txt, mode=chemistry_mode)
    if n_matl_fix:
        print(f"  [fix] 已补全 {n_matl_fix} 个可燃 MATL 的热解产物链"
              f"（chemistry={chem_tag}，修复 HRR=0）")

    if keep_burn_away or bst_mode:
        txt, n_ba = FMV.apply_burn_away_to_comb_surfs(txt)
        if n_ba:
            print(f"  [fix] 已为 {n_ba} 个可燃 base SURF 启用 BURN_AWAY"
                  f"（受照 OBST 将注入 BULK_DENSITY）")

    if seal_enclosure:
        txt, n_seal = FMV.apply_seal_enclosure(txt)
        if n_seal:
            print(f"  [fix] 已密封舱体：移除 {n_seal} 个 ZMAX OPEN 边界")

    if patch_gaps:
        txt, n_gap = FMV.apply_patch_enclosure_gaps(txt)
        if n_gap:
            print(f"  [fix] 已补封闭缝隙：新增 {n_gap} 块端面/顶面 OBST")

    # ── 可选：加厚可燃 SURF 层（thickmatl 变体）────────────────────────
    if thickness_scale is not None:
        txt, n_thick = FMV.apply_thickness_scale(txt, scale=thickness_scale)
        if n_thick:
            print(f"  [fix] 已加厚 {n_thick} 个可燃 SURF"
                  f"（THICKNESS ×{thickness_scale:g}）")

    # ── 可选：文献核对表参数变体（low_hor / reac20 / …）────────────────
    if param_profile is not None:
        txt, plogs, vid = FMV.apply_param_variant(txt, param_profile)
        cfg = FMV.PARAM_VARIANTS[vid]
        if not cfg.get('disabled'):
            print(f"  [fix] 参数变体 {vid}: {cfg['title']}")
            for step, n in plogs:
                print(f"        · {step}: {n} 处")

    # 安全网：默认剥离 IGNITION/BURN_AWAY；BST 变体保留二者
    txt, n_strip = FMV.strip_incompatible_surf_flags(
        txt,
        keep_burn_away=(keep_burn_away or bst_mode),
        keep_ignition=bst_mode,
    )
    if n_strip and not bst_mode:
        msg = "IGNITION_TEMPERATURE"
        if not keep_burn_away:
            msg += "/BURN_AWAY"
        print(f"  [fix] 已剥离 {n_strip} 个 SURF 上的 {msg}（避免 ERROR 335/607）")

    # ── 剥离零体积 OBST 的 BULK_DENSITY（修复 FDS ERROR 611）─────────────
    # PyroSim 给薄板 OBST 写了 BULK_DENSITY，但零体积无法计算质量。
    # 质量/热解信息已由 SURF 的 MATL+THICKNESS 承担，BULK_DENSITY 直接删除。
    n_bulk_fix = 0
    for m in list(re.finditer(r'&OBST[^/]*BULK_DENSITY[^/]*/', txt)):
        raw = m.group()
        xm = re.search(r'XB=([-\d.E+,\s]+?),\s*[A-Z]', raw)
        if not xm:
            continue
        try:
            v = [float(x) for x in xm.group(1).split(',')][:6]
        except ValueError:
            continue
        vol = abs(v[1]-v[0]) * abs(v[3]-v[2]) * abs(v[5]-v[4])
        if vol < 1e-12:
            cleaned = re.sub(r",?\s*BULK_DENSITY\s*=\s*[\d.E+-]+", '', raw)
            txt = txt.replace(raw, cleaned, 1)
            n_bulk_fix += 1
    if n_bulk_fix:
        print(f"  [fix] 已剥离 {n_bulk_fix} 个零体积 OBST 的 BULK_DENSITY（ERROR 611）")
    blocks = defaultdict(list)
    obs = []
    for m in re.finditer(r'(&\w+[\s\S]*?/)', txt):
        raw = m.group(1)
        tp  = re.match(r'&(\w+)', raw).group(1)
        if tp != 'OBST':
            blocks[tp].append(raw)
            continue
        xm = re.search(r'XB=\s*([-\d.E+,\s]+?)(?:,\s*[A-Z]|/)', raw)
        if not xm:
            blocks['OBST_OTHER'].append(raw); continue
        try:
            vals = [float(v.strip()) for v in xm.group(1).split(',') if v.strip()][:6]
        except ValueError:
            blocks['OBST_OTHER'].append(raw); continue
        if len(vals) < 6:
            blocks['OBST_OTHER'].append(raw); continue
        sid = re.search(r"SURF_ID\s*=\s*'([^']+)'", raw)
        surf = sid.group(1) if sid else ''
        obs.append(dict(xb=vals, surf=surf, raw=raw,
                        comb=surf in COMB_SURFS,
                        flux_recv=surf in FLUX_RECV_SURFS,
                        idx=len(obs)))
    return txt, blocks, obs


def get_mesh_domain(blocks):
    """从 &MESH 提取计算域边界。多 MESH 时取所有 MESH 的并集包围盒
    （本模型有 MESH01+MESH02 两块，需覆盖两者）。"""
    boxes = []
    for raw in blocks.get('MESH', []):
        # XB 后可能还有 MPI_PROCESS=…/，不能要求 XB 后立刻 /
        m = re.search(r'XB=\s*([-\d.E+,\s]+?)(?:,\s*[A-Z_]|/)', raw)
        if m:
            v = [float(x.strip()) for x in m.group(1).split(',') if x.strip()][:6]
            if len(v) == 6:
                boxes.append(v)
    if not boxes:
        raise RuntimeError('未找到 &MESH 块')
    arr = list(zip(*boxes))
    return (min(arr[0]), max(arr[1]), min(arr[2]), max(arr[3]),
            min(arr[4]), max(arr[5]))


def detect_mesh_resolutions(blocks):
    """探测所有 &MESH 的格距，用于报告混合分辨率情况。
       返回 [(mesh_id, dx, dy, dz, ncell), ...]。"""
    res = []
    for raw in blocks.get('MESH', []):
        mi = re.search(r'IJK=(\d+),(\d+),(\d+)', raw)
        mx = re.search(r'XB=\s*([-\d.E+,\s]+)/', raw)
        mid = re.search(r"ID='([^']*)'", raw)
        if mi and mx:
            I, J, K = int(mi.group(1)), int(mi.group(2)), int(mi.group(3))
            v = [float(x.strip()) for x in mx.group(1).split(',') if x.strip()][:6]
            if len(v) == 6:
                res.append((mid.group(1) if mid else '?',
                            (v[1]-v[0])/I, (v[3]-v[2])/J, (v[5]-v[4])/K, I*J*K))
    return res



# ══════════════════════════════════════════════════════════════════════════════
# §3  体素遮挡网格（改进体素法核心）
# ══════════════════════════════════════════════════════════════════════════════
def build_voxel_grids(obs, domain, pitch=DDA_PITCH):
    """
    构建两套体素网格：
      g_opaque : 不透明遮挡（铝合金等）→ bool
      g_glass  : 玻璃（丙烯酸）→ int32（OBST 索引+1，per-OBST 透射率追踪）

    边界修正：当 OBST 上界恰好落在体素边界（v/pitch 为整数）时收缩 1 格，
    防止零厚度薄板膨胀为 2 层体素。
    """
    xo, yo, zo = domain[0], domain[2], domain[4]
    nx = int(np.ceil((domain[1]-xo)/pitch)) + 2
    ny = int(np.ceil((domain[3]-yo)/pitch)) + 2
    nz = int(np.ceil((domain[5]-zo)/pitch)) + 2
    g_opaque = np.zeros((nx, ny, nz), dtype=bool)
    g_glass  = np.zeros((nx, ny, nz), dtype=np.int32)

    def lo_hi(v0, v1, n):
        lo  = max(0, int(np.floor(v0/pitch)))
        raw = int(np.ceil(v1/pitch))
        hi  = raw-1 if abs(v1/pitch - round(v1/pitch)) < 1e-9 else raw
        hi  = max(lo, hi)
        return lo, min(n-1, hi)

    for ob in obs:
        x0,x1 = min(ob['xb'][0],ob['xb'][1]), max(ob['xb'][0],ob['xb'][1])
        y0,y1 = min(ob['xb'][2],ob['xb'][3]), max(ob['xb'][2],ob['xb'][3])
        z0,z1 = min(ob['xb'][4],ob['xb'][5]), max(ob['xb'][4],ob['xb'][5])
        ix0,ix1 = lo_hi(x0-xo, x1-xo, nx)
        iy0,iy1 = lo_hi(y0-yo, y1-yo, ny)
        iz0,iz1 = lo_hi(z0-zo, z1-zo, nz)
        if ob['surf'] in GLASS_SURFS:
            g_glass[ix0:ix1+1, iy0:iy1+1, iz0:iz1+1] = ob['idx'] + 1
        elif ob['surf'] in OPAQUE_SURFS:
            g_opaque[ix0:ix1+1, iy0:iy1+1, iz0:iz1+1] = True
        # 可燃薄板自身不入遮挡网格（避免自遮挡假象）；
        # 注意：可燃物之间的互相遮挡由"前层玻璃/帘"的玻璃网格近似处理

    return g_opaque, g_glass, (xo, yo, zo, nx, ny, nz)


def dda_ray(origin, u, g_opaque, g_glass, grid_info,
            pitch=DDA_PITCH, trans=GLASS_TRANS):
    """
    Amanatides-Woo DDA 体素遍历。
    返回透射率 [0,1]：0=被不透明体遮挡；穿过 n 层玻璃 → 0.85^n。
    per-OBST 玻璃追踪：同一玻璃 OBST 的多个体素只衰减一次。
    """
    xo, yo, zo, nx, ny, nz = grid_info
    ox=(origin[0]-xo)/pitch; oy=(origin[1]-yo)/pitch; oz=(origin[2]-zo)/pitch
    dx, dy, dz = u
    ix,iy,iz = int(np.floor(ox)), int(np.floor(oy)), int(np.floor(oz))
    sx = 1 if dx > 0 else -1
    sy = 1 if dy > 0 else -1
    sz = 1 if dz > 0 else -1
    tx = ((ix+(1 if dx>0 else 0))-ox)/dx if abs(dx) > 1e-12 else np.inf
    ty = ((iy+(1 if dy>0 else 0))-oy)/dy if abs(dy) > 1e-12 else np.inf
    tz = ((iz+(1 if dz>0 else 0))-oz)/dz if abs(dz) > 1e-12 else np.inf
    dtx = abs(1/dx) if abs(dx) > 1e-12 else np.inf
    dty = abs(1/dy) if abs(dy) > 1e-12 else np.inf
    dtz = abs(1/dz) if abs(dz) > 1e-12 else np.inf

    tr = 1.0
    visited = set()
    for _ in range(nx+ny+nz+4):
        if not (0 <= ix < nx and 0 <= iy < ny and 0 <= iz < nz):
            return tr                      # 射出计算域 → 到达爆点方向
        if g_opaque[ix, iy, iz]:
            return 0.0                     # 不透明遮挡
        gid = g_glass[ix, iy, iz]
        if gid > 0 and gid not in visited:
            visited.add(gid)
            tr *= trans
            if tr < 0.005:
                return 0.0
        if tx <= ty and tx <= tz: ix += sx; tx += dtx
        elif ty <= tz:            iy += sy; ty += dty
        else:                     iz += sz; tz += dtz
    return tr


# ══════════════════════════════════════════════════════════════════════════════
# §4  薄板面几何
# ══════════════════════════════════════════════════════════════════════════════
def plate_orientation(xb, tol=1e-6):
    """零厚度薄板的法向轴：'x' / 'y' / 'z'；非薄板返回 None。"""
    dx = abs(xb[1]-xb[0]); dy = abs(xb[3]-xb[2]); dz = abs(xb[5]-xb[4])
    if dx < tol: return 'x'
    if dy < tol: return 'y'
    if dz < tol: return 'z'
    return None


def illuminated_face(xb, u, tol=1e-6):
    """
    确定薄板受照面方向（返回 '-x'/'+x'/... 或 None）。
    薄板法向轴为 n；受照面是迎向太阳的那一侧：sign = u·n_axis。
    对非薄板（3D OBST），返回所有 cosθ>0 的面列表。
    """
    axis = plate_orientation(xb, tol)
    if axis is not None:
        comp = {'x': u[0], 'y': u[1], 'z': u[2]}[axis]
        if abs(comp) < 1e-9:
            return []           # 太阳平行于薄板，无照射
        return [('+' if comp > 0 else '-') + axis]
    return [fd for fd, fn in FN.items() if float(np.dot(fn, u)) > 1e-6]


def face_frame(xb, fd):
    """
    受照面参数化：(fc, a0,a1, b0,b1, ax_a, ax_b)
      fc        : 面所在轴向坐标
      (a,b)     : 面内两个切向坐标区间
      ax_a/ax_b : 切向坐标对应的轴名（用于还原 3D 坐标）
    """
    x0,x1 = min(xb[0],xb[1]), max(xb[0],xb[1])
    y0,y1 = min(xb[2],xb[3]), max(xb[2],xb[3])
    z0,z1 = min(xb[4],xb[5]), max(xb[4],xb[5])
    table = {
        '-x': (x0, y0,y1, z0,z1, 'y', 'z'),
        '+x': (x1, y0,y1, z0,z1, 'y', 'z'),
        '-y': (y0, x0,x1, z0,z1, 'x', 'z'),
        '+y': (y1, x0,x1, z0,z1, 'x', 'z'),
        '-z': (z0, x0,x1, y0,y1, 'x', 'y'),
        '+z': (z1, x0,x1, y0,y1, 'x', 'y'),
    }
    return table[fd]


def make_origin(fc, fd, a, b):
    """由面坐标 + 面内 (a,b) 还原三维点。"""
    if fd in ('-x', '+x'): return np.array([fc, a, b])
    if fd in ('-y', '+y'): return np.array([a, fc, b])
    return np.array([a, b, fc])


# ══════════════════════════════════════════════════════════════════════════════
# §5  逐 OBST / 逐子片热流计算
# ══════════════════════════════════════════════════════════════════════════════
def qz(v, step=FLUX_STEP):
    return round(v/step)*step


def compute_obst_flux(ob, u, E0, g_opaque, g_glass, grid_info):
    """
    计算一个可燃 OBST 的受照热流。

    返回值
    ------
    list of (sub_xb, fd, flux)
      sub_xb : 子 OBST 的 XB（大面板分割后的子片；小面板=原 XB）
      fd     : 受照面方向
      flux   : 量化后的 EXTERNAL_FLUX (kW/m²)；0 表示阴影
    """
    xb = ob['xb']
    faces = illuminated_face(xb, u)
    if not faces:
        return []

    results = []
    for fd in faces:
        fn = FN[fd]
        ct = float(np.dot(fn, u))
        if ct <= 1e-6:
            continue
        fc, a0, a1, b0, b1, ax_a, ax_b = face_frame(xb, fd)
        da, db = a1-a0, b1-b0

        # ── 决定是否分割 ────────────────────────────────────────────────
        na = max(1, int(np.ceil(da/PATCH_RES))) if da > SPLIT_MIN else 1
        nb = max(1, int(np.ceil(db/PATCH_RES))) if db > SPLIT_MIN else 1
        ae = np.linspace(a0, a1, na+1)
        be = np.linspace(b0, b1, nb+1)

        # ── 逐子片采样 ─────────────────────────────────────────────────
        patch_flux = np.zeros((na, nb))
        for i in range(na):
            for j in range(nb):
                # 2×2 采样点
                aa = np.linspace(ae[i], ae[i+1], N_SAMPLE+2)[1:-1]
                bb = np.linspace(be[j], be[j+1], N_SAMPLE+2)[1:-1]
                tot = 0.; cnt = 0
                for av in aa:
                    for bv in bb:
                        # Move one complete voxel toward the source. The old
                        # 0.6-pitch offset could remain inside the receiver's
                        # own opaque voxel, falsely shadowing aluminium.
                        org = make_origin(fc, fd, av, bv) + u*(DDA_PITCH*1.1)
                        tot += dda_ray(org, u, g_opaque, g_glass, grid_info)
                        cnt += 1
                patch_flux[i, j] = qz(ct * E0 * (tot/cnt))

        # ── 行列合并（相同 flux 的相邻子片 → 矩形）─────────────────────
        if na == 1 and nb == 1:
            merged = [(a0, a1, b0, b1, patch_flux[0, 0])]
        else:
            merged = merge_rects(patch_flux, ae, be)

        # ── 还原子 OBST XB ──────────────────────────────────────────────
        for (ma0, ma1, mb0, mb1, fq) in merged:
            sub = list(xb)
            ia = {'x': 0, 'y': 2, 'z': 4}[ax_a]
            ib = {'x': 0, 'y': 2, 'z': 4}[ax_b]
            sub[ia], sub[ia+1] = ma0, ma1
            sub[ib], sub[ib+1] = mb0, mb1
            results.append((sub, fd, fq))
    return results


def merge_rects(Q, ae, be):
    """行条带 + 纵向合并：相邻同值子片 → 最小矩形集。"""
    na, nb = Q.shape
    rows = []
    for i in range(na):
        strips, j = [], 0
        while j < nb:
            f = Q[i, j]; k = j+1
            while k < nb and Q[i, k] == f: k += 1
            strips.append((j, k, f)); j = k
        rows.append(tuple(strips))
    rects, i = [], 0
    while i < na:
        pat = rows[i]; e = i+1
        while e < na and rows[e] == pat: e += 1
        for (j0, j1, f) in pat:
            rects.append((ae[i], ae[e], be[j0], be[j1], f))
        i = e
    return rects


# ══════════════════════════════════════════════════════════════════════════════
# §6  DEVC / SLCF / BNDF 注入
# ══════════════════════════════════════════════════════════════════════════════
def build_monitor_blocks(domain, flux_records, top_n=8):
    """
    生成监测块：
      ① 热流 Top-N 可燃面 → WALL TEMPERATURE + NET HEAT FLUX 测点
      ② 三舱段气相测点 → TEMPERATURE / O2 / CO / SOOT / VISIBILITY
      ③ SLCF 观测平面 → 中纵剖面 / 三横截面 / 呼吸层（温度、O2、HRRPUV）
      ④ BNDF → WALL TEMPERATURE / NET HEAT FLUX / BURNING RATE
      ⑤ 全域 HRR、烟层高度
    """
    x0, x1, y0, y1, z0, z1 = domain
    xc  = (x0+x1)/2
    L   = []

    # ① 高热流可燃面测点 -------------------------------------------------
    L.append("! ══ ① 高热流可燃面测点（壁温 + 净热流）══")
    recs = sorted(flux_records, key=lambda r: -r['flux'])[:top_n]
    IOR_MAP = {'-x': -1, '+x': 1, '-y': -2, '+y': 2, '-z': -3, '+z': 3}
    cell = 0.1   # Mesh01 主域格距 (m)
    eps  = max(0.015, min(cell * 0.49, cell * 0.35))
    for k, r in enumerate(recs):
        sx  = r['sub_xb']; fd = r['fd']
        cx  = (sx[0]+sx[1])/2; cy = (sx[2]+sx[3])/2
        if fd == '-x':
            cx, cy, cz = sx[0]-eps, cy, (sx[4]+sx[5])/2
        elif fd == '+x':
            cx, cy, cz = sx[1]+eps, cy, (sx[4]+sx[5])/2
        elif fd == '-y':
            cx, cy, cz = cx, sx[2]-eps, (sx[4]+sx[5])/2
        elif fd == '+y':
            cx, cy, cz = cx, sx[3]+eps, (sx[4]+sx[5])/2
        elif fd == '-z':
            cx, cy, cz = cx, cy, sx[4]-eps
        else:  # +z
            cx, cy, cz = cx, cy, sx[5]+eps
        ior = IOR_MAP[fd]
        tag = f"F{k:02d}_{r['mat']}_{r['flux']:.0f}"
        L.append(f"&DEVC ID='{tag}_WT', QUANTITY='WALL TEMPERATURE',"
                 f" XYZ={cx:.3f},{cy:.3f},{cz:.3f}, IOR={ior} /")
        L.append(f"&DEVC ID='{tag}_NHF', QUANTITY='NET HEAT FLUX',"
                 f" XYZ={cx:.3f},{cy:.3f},{cz:.3f}, IOR={ior} /")

    # ② 三舱段气相测点 ----------------------------------------------------
    L.append("\n! ══ ② 舱段气相环境测点（前/中/后 ×2 高度）══")
    stations = [('fore', x0+0.25*(x1-x0)), ('mid', xc), ('aft', x0+0.75*(x1-x0))]
    heights  = [('breath', 0.8), ('head', 1.4)]
    for sname, sx in stations:
        for hname, hz in heights:
            L.append(f"&DEVC ID='T_{sname}_{hname}', QUANTITY='TEMPERATURE',"
                     f" XYZ={sx:.2f},{(y0+y1)/2:.2f},{hz:.2f} /")
        L.append(f"&DEVC ID='O2_{sname}',  QUANTITY='VOLUME FRACTION',"
                 f" SPEC_ID='OXYGEN', XYZ={sx:.2f},{(y0+y1)/2:.2f},0.8 /")
        L.append(f"&DEVC ID='CO_{sname}',  QUANTITY='VOLUME FRACTION',"
                 f" SPEC_ID='CARBON MONOXIDE', XYZ={sx:.2f},{(y0+y1)/2:.2f},0.8 /")
        L.append(f"&DEVC ID='VIS_{sname}', QUANTITY='VISIBILITY',"
                 f" XYZ={sx:.2f},{(y0+y1)/2:.2f},0.8 /")

    # ③ 全域指标 ----------------------------------------------------------
    # 注意：XB 型 DEVC 必须完全位于域内。坐标取整可能越界（ERROR 937），
    # 因此所有 XB 区域向内收缩一个网格（0.05m）。
    ins = 0.05
    ix0, ix1 = x0+ins, x1-ins
    iy0, iy1 = y0+ins, y1-ins
    iz0, iz1 = z0+ins, z1-ins
    ym = (y0+y1)/2
    L.append("\n! ══ ③ 全域指标 ══")
    L.append(f"&DEVC ID='HRR_total', QUANTITY='HRR',"
             f" XB={ix0:.3f},{ix1:.3f},{iy0:.3f},{iy1:.3f},{iz0:.3f},{iz1:.3f} /")
    # LAYER HEIGHT 要求竖直线段（x0=x1, y0=y1）：在前/中/后三站布置
    for sname, sx in stations:
        L.append(f"&DEVC ID='LAYER_{sname}', QUANTITY='LAYER HEIGHT',"
                 f" XB={sx:.2f},{sx:.2f},{ym:.2f},{ym:.2f},{iz0:.3f},{iz1:.3f} /")
    L.append(f"&DEVC ID='O2_min_global', QUANTITY='VOLUME FRACTION',"
             f" SPEC_ID='OXYGEN', SPATIAL_STATISTIC='MIN',"
             f" XB={ix0:.3f},{ix1:.3f},{iy0:.3f},{iy1:.3f},0.4,1.6 /")

    # ④ SLCF 观测平面 -----------------------------------------------------
    L.append("\n! ══ ④ SLCF 观测平面 ══")
    L.append(f"&SLCF PBY={(y0+y1)/2:.2f}, QUANTITY='TEMPERATURE' /        ! 中纵剖面")
    L.append(f"&SLCF PBY={(y0+y1)/2:.2f}, QUANTITY='HRRPUV' /")
    L.append(f"&SLCF PBY={(y0+y1)/2:.2f}, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN' /")
    for label, px in [('cockpit', x0+0.2*(x1-x0)), ('mid', xc), ('aft', x0+0.8*(x1-x0))]:
        L.append(f"&SLCF PBX={px:.2f}, QUANTITY='TEMPERATURE' /          ! {label} 横截面")
    L.append(f"&SLCF PBZ=0.80, QUANTITY='TEMPERATURE' /                  ! 呼吸层")
    L.append(f"&SLCF PBZ=0.80, QUANTITY='VOLUME FRACTION', SPEC_ID='OXYGEN' /")
    L.append(f"&SLCF PBZ=0.80, QUANTITY='VOLUME FRACTION', SPEC_ID='CARBON MONOXIDE' /")

    # ⑤ BNDF --------------------------------------------------------------
    L.append("\n! ══ ⑤ BNDF 边界场 ══")
    L.append("&BNDF QUANTITY='WALL TEMPERATURE' /")
    L.append("&BNDF QUANTITY='NET HEAT FLUX' /")
    L.append("&BNDF QUANTITY='BURNING RATE' /")
    return L


# ══════════════════════════════════════════════════════════════════════════════
# §7  FDS 输出
# ══════════════════════════════════════════════════════════════════════════════
def write_fds(src_txt, obs, surf_variants, obst_replacements,
              monitor_lines, out_path, header_note):
    """
    生成新 FDS：
      - 原文中每个被替换的可燃 OBST 行 → 一组新 OBST 行（SURF_ID6 变体）
      - &TAIL 前插入：辐射 SURF 变体 + 监测块
    """
    txt = src_txt

    # ── 替换可燃 OBST ──────────────────────────────────────────────────
    for raw, new_lines in obst_replacements.items():
        txt = txt.replace(raw, '\n'.join(new_lines), 1)

    # ── SURF 变体块 ────────────────────────────────────────────────────
    sv_lines = [f"\n! ══ 辐射 SURF 变体（{len(surf_variants)} 个，"
                f"EXTERNAL_FLUX × RAMP_EF='NUCLEAR_RAMP'）══"]
    for sv, info in sorted(surf_variants.items(), key=lambda x: x[1]['flux']):
        base = info['base_raw'].rstrip().rstrip('/')
        sv_lines.append(
            re.sub(r"ID='[^']+'", f"ID='{sv}'", base, count=1)
            + f",\n      EXTERNAL_FLUX={info['flux']:.0f},"
              f" RAMP_EF='NUCLEAR_RAMP'/")

    inject = '\n'.join(sv_lines) + '\n\n' + '\n'.join(monitor_lines) + '\n\n&TAIL'
    if '&TAIL' in txt:
        txt = txt.replace('&TAIL', inject, 1)
    else:
        txt += '\n' + inject + ' /\n'

    # 改写 CHID 为工况名（避免所有文件 CHID 相同）
    new_chid = Path(out_path).stem
    txt = re.sub(r"(&HEAD[^/]*CHID=')[^']+(')",
                 rf"\g<1>{new_chid}\g<2>", txt, count=1)

    hdr = (f"! {'='*70}\n! {header_note}\n! {'='*70}\n")
    Path(out_path).write_text(hdr + txt, encoding='utf-8')


# ══════════════════════════════════════════════════════════════════════════════
# §8  热流分布可视化 + 数据导出
# ══════════════════════════════════════════════════════════════════════════════
def _mat_label(abbr):
    return MAT_ABBR_ZH.get(abbr, abbr)


def _write_flux_csv(flux_records, csv_path):
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['x0', 'x1', 'y0', 'y1', 'z0', 'z1', 'face', 'material',
                    'surf_variant', 'flux_kW_m2', 'cos_theta'])
        for r in flux_records:
            w.writerow([*[f'{v:.4f}' for v in r['sub_xb']], r['fd'], r['mat'],
                        r['sv'], f"{r['flux']:.0f}", f"{r['ct']:.4f}"])


def _plot_flux_distribution(xs, ys, zs, qs, scenario_tag, E0, az, el, n_faces, out_path):
    fig = plt.figure(figsize=(17, 10))
    fig.suptitle(
        f'体素法受照面热流三维分布 — {scenario_tag}\n'
        f'初始热流 E0={E0:.0f} kW/m²，方位角 az={az:.0f}°，仰角 el={el:.1f}°  |  '
        f'受照子面 {n_faces} 个，最大热流 q_max={qs.max():.0f} kW/m²',
        fontsize=12, fontweight='bold')

    ax3d = fig.add_subplot(2, 2, 1, projection='3d')
    sc = ax3d.scatter(xs, ys, zs, c=qs, cmap='hot', s=14, vmin=0, vmax=qs.max())
    ax3d.set_xlabel('X (m)'); ax3d.set_ylabel('Y (m)'); ax3d.set_zlabel('Z (m)')
    ax3d.set_title('三维散点（颜色=入射热流 q）', fontsize=10, fontweight='bold')
    fig.colorbar(sc, ax=ax3d, fraction=0.03, pad=0.08, label='热流 q (kW/m²)')

    for sp, (u_ax, v_ax, u_d, v_d, title) in zip(
            [2, 3, 4],
            [(xs, zs, 'X (m)', 'Z (m)', '侧视投影 (X-Z)'),
             (xs, ys, 'X (m)', 'Y (m)', '俯视投影 (X-Y)'),
             (ys, zs, 'Y (m)', 'Z (m)', '正视投影 (Y-Z)')]):
        ax = fig.add_subplot(2, 2, sp)
        s = ax.scatter(u_ax, v_ax, c=qs, cmap='hot', s=18, vmin=0, vmax=qs.max())
        ax.set_xlabel(u_d); ax.set_ylabel(v_d)
        ax.set_title(title, fontsize=10, fontweight='bold')
        ax.set_aspect('equal'); ax.grid(alpha=0.25)
        fig.colorbar(s, ax=ax, fraction=0.04, pad=0.03, label='热流 q (kW/m²)')

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()


def _plot_flux_stats(qs, mat_abbrs, scenario_tag, out_path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.5))
    fig.suptitle(f'体素法热流统计 — {scenario_tag}', fontsize=11, fontweight='bold')
    ax1.hist(qs, bins=24, color='#C62828', alpha=0.85, edgecolor='white')
    ax1.set_xlabel('入射热流 q (kW/m²)'); ax1.set_ylabel('受照子面数量')
    ax1.set_title('热流量级分布直方图', fontsize=10, fontweight='bold')
    ax1.grid(alpha=0.3, axis='y')

    mats = Counter(mat_abbrs)
    mat_keys = list(mats.keys())
    mat_labels = [_mat_label(k) for k in mat_keys]
    ax2.barh(mat_labels, [mats[k] for k in mat_keys],
             color='#1565C0', alpha=0.85, edgecolor='white')
    ax2.set_xlabel('受照子面数量')
    ax2.set_title('各材料受照子面数量', fontsize=10, fontweight='bold')
    ax2.grid(alpha=0.3, axis='x')
    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches='tight', facecolor='white')
    plt.close()


def plot_flux_from_csv(csv_path, out_dir, E0, az, el, scenario_tag=None, also_figures=None):
    """从已有 flux CSV 重绘三维分布图与统计图。"""
    csv_path = Path(csv_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tag = scenario_tag or csv_path.stem.replace('flux_', '', 1)

    rows = list(csv.DictReader(open(csv_path, encoding='utf-8-sig')))
    if not rows:
        print(f'  [warn] {csv_path.name} 为空，跳过')
        return None, None

    xs = np.array([(float(r['x0']) + float(r['x1'])) / 2 for r in rows])
    ys = np.array([(float(r['y0']) + float(r['y1'])) / 2 for r in rows])
    zs = np.array([(float(r['z0']) + float(r['z1'])) / 2 for r in rows])
    qs = np.array([float(r['flux_kW_m2']) for r in rows])
    mat_abbrs = [r['material'] for r in rows]

    png3d = out / f'flux_{tag}.png'
    png_stats = out / f'flux_stats_{tag}.png'
    _plot_flux_distribution(xs, ys, zs, qs, tag, E0, az, el, len(rows), png3d)
    _plot_flux_stats(qs, mat_abbrs, tag, png_stats)

    if also_figures:
        import shutil
        fig_dir = Path(also_figures)
        fig_dir.mkdir(parents=True, exist_ok=True)
        for src in (png3d, png_stats):
            shutil.copy2(src, fig_dir / src.name)
    print(f'  重绘: {png3d.name}, {png_stats.name} ← {csv_path.name}')
    return png3d, png_stats


def export_flux(flux_records, scenario_tag, out_dir, E0, az, el):
    """导出热流分布：3D 散点 + 三视图投影 PNG + CSV。"""
    out = Path(out_dir)
    if not flux_records:
        print('  [warn] 无受照面，跳过绘图')
        return

    xs = np.array([(r['sub_xb'][0]+r['sub_xb'][1])/2 for r in flux_records])
    ys = np.array([(r['sub_xb'][2]+r['sub_xb'][3])/2 for r in flux_records])
    zs = np.array([(r['sub_xb'][4]+r['sub_xb'][5])/2 for r in flux_records])
    qs = np.array([r['flux'] for r in flux_records])
    mat_abbrs = [r['mat'] for r in flux_records]

    csv_path = out / f'flux_{scenario_tag}.csv'
    _write_flux_csv(flux_records, csv_path)

    png_path = out / f'flux_{scenario_tag}.png'
    _plot_flux_distribution(xs, ys, zs, qs, scenario_tag, E0, az, el,
                            len(flux_records), png_path)
    _plot_flux_stats(qs, mat_abbrs, scenario_tag,
                     out / f'flux_stats_{scenario_tag}.png')

    print(f'  导出: {png_path.name}, flux_stats_{scenario_tag}.png, {csv_path.name}')


# ══════════════════════════════════════════════════════════════════════════════
# §9  单工况处理主函数
# ══════════════════════════════════════════════════════════════════════════════
def run_scenario(fds_path, E0, az, el, label, out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    tag = f"{label}_az{az:03.0f}_el{el:02.0f}"
    u   = sun_vec(az, el)

    print(f"\n{'─'*64}")
    print(f"  工况 {tag}:  E0={E0:.0f} kW/m²  u={u.round(3)}")
    t0 = time.time()

    src_txt, blocks, obs = parse_fds(fds_path)
    domain = get_mesh_domain(blocks)
    # 可燃 + 铝合金均接收 EXTERNAL_FLUX（铝合金同时仍作遮挡）
    flux_obs = [o for o in obs if o.get('flux_recv') or o['comb']]
    n_al = sum(1 for o in flux_obs if o['surf'] in AL_FLUX_SURFS)
    print(f"  OBST: {len(obs)}（赋通量 {len(flux_obs)}，其中铝合金 {n_al}）  域: "
          f"X[{domain[0]:.2f},{domain[1]:.2f}]")

    # 体素网格
    g_op, g_gl, gi = build_voxel_grids(obs, domain)
    print(f"  体素网格: {gi[3]}×{gi[4]}×{gi[5]}  "
          f"不透明 {g_op.sum()}  玻璃体素 {(g_gl>0).sum()}")

    # SURF base 原文映射（用于变体生成）
    surf_base_raw = {}
    for raw in blocks.get('SURF', []):
        m = re.search(r"ID='([^']+)'", raw)
        if m: surf_base_raw[m.group(1)] = raw

    # 逐 OBST 热流
    surf_variants = {}      # sv → {flux, base_raw}
    obst_repl     = {}      # 原 raw → [新行]
    flux_records  = []      # 用于可视化
    n_lit = 0

    for ob in flux_obs:
        subs = compute_obst_flux(ob, u, E0, g_op, g_gl, gi)
        if not subs:
            continue
        lit_subs = [(s, fd, fq) for (s, fd, fq) in subs if fq > 0]
        if not lit_subs:
            continue

        n_lit += 1
        base_cn = ob['surf']
        abbr    = FLUX_RECV_MAP[base_cn]
        new_lines = [f"! per-voxel split of OBST #{ob['idx']} ({base_cn})"]
        ior_pos = {'-x':0,'+x':1,'-y':2,'+y':3,'-z':4,'+z':5}

        # 阴影子片：保留 base SURF
        shadow_subs = [(s, fd, fq) for (s, fd, fq) in subs if fq <= 0]
        for (s, fd, fq) in shadow_subs:
            xbs = ','.join(f'{v:.6f}' for v in s)
            new_lines.append(f"&OBST XB={xbs}, SURF_ID='{base_cn}' /")

        bulk_rho = None
        if _BURN_AWAY_OBST_MODE and base_cn in COMB_SURFS:
            import fds_material_variants as FMV
            bulk_rho = FMV.COMB_SURF_BULK_RHO.get(base_cn)

        for (s, fd, fq) in lit_subs:
            sv = f"{abbr}_R{int(fq):04d}"
            if sv not in surf_variants:
                surf_variants[sv] = dict(flux=fq,
                                         base_raw=surf_base_raw[base_cn])
            faces = [f"'{base_cn}'"]*6
            faces[ior_pos[fd]] = f"'{sv}'"
            sb = list(s)
            if bulk_rho is not None:
                # 零厚度薄板：给最小 10 mm 实体厚度，以便 BULK_DENSITY + BURN_AWAY（FDS 607）
                for i in range(3):
                    if abs(sb[2 * i + 1] - sb[2 * i]) < 1e-9:
                        mid = sb[2 * i]
                        sb[2 * i] = mid - 0.005
                        sb[2 * i + 1] = mid + 0.005
            xbs = ','.join(f'{v:.6f}' for v in sb)
            line = f"&OBST XB={xbs}, SURF_ID6={','.join(faces)}"
            if bulk_rho is not None:
                vol = abs(sb[1] - sb[0]) * abs(sb[3] - sb[2]) * abs(sb[5] - sb[4])
                if vol > 1e-9:
                    line += f", BULK_DENSITY={bulk_rho:.1f}"
            line += " /"
            new_lines.append(line)
            ct = float(np.dot(FN[fd], u))
            flux_records.append(dict(sub_xb=s, fd=fd, flux=fq, sv=sv,
                                     mat=abbr, ct=ct))
        obst_repl[ob['raw']] = new_lines

    el_t = time.time() - t0
    print(f"  受照 OBST: {n_lit}/{len(flux_obs)}  "
          f"子片: {len(flux_records)}  SURF 变体: {len(surf_variants)}  "
          f"耗时 {el_t:.1f}s")

    # 监测块 & 输出
    monitor = build_monitor_blocks(domain, flux_records)
    out_fds = out / f"jitou_v5_{tag}.fds"
    note = (f"per-voxel flux  {tag}  E0={E0:.0f}kW/m2 az={az} el={el}  "
            f"lit_subfaces={len(flux_records)}")
    write_fds(src_txt, obs, surf_variants, obst_repl, monitor,
              str(out_fds), note)
    print(f"  FDS 输出: {out_fds.name}  "
          f"({out_fds.stat().st_size/1024:.0f} KB)")

    export_flux(flux_records, tag, out, E0, az, el)

    # 工况摘要 JSON
    summary = dict(tag=tag, E0=E0, az=az, el=el,
                   lit_obst=n_lit, sub_faces=len(flux_records),
                   surf_variants=len(surf_variants),
                   max_flux=max((r['flux'] for r in flux_records), default=0),
                   material_counts=dict(Counter(r['mat'] for r in flux_records)))
    (out / f'summary_{tag}.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


# ══════════════════════════════════════════════════════════════════════════════
# §10  Main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description='核爆光辐射逐体素热流 FDS 生成器')
    ap.add_argument('--fds', default='./jitou_20260609_v5.fds')
    ap.add_argument('--out', default='./flux_output')
    ap.add_argument('--E0',  type=float, default=1287.)
    ap.add_argument('--az',  type=float, default=270.)
    ap.add_argument('--el',  type=float, default=26.57)
    ap.add_argument('--label', default='E3_100kt')
    ap.add_argument('--all-scenarios', action='store_true',
                    help='批量运行预设 10 工况')
    args = ap.parse_args()

    if not Path(args.fds).exists():
        print(f'ERROR: 找不到 {args.fds}'); return

    print('='*64)
    print('  核爆光辐射 → 逐体素热流 → FDS 火灾仿真文件生成')
    print(f'  输入: {args.fds}')
    print('='*64)

    summaries = []
    if args.all_scenarios:
        for (label, E0, az, el) in SCENARIOS:
            summaries.append(run_scenario(args.fds, E0, az, el, label, args.out))
    else:
        summaries.append(run_scenario(args.fds, args.E0, args.az, args.el,
                                      args.label, args.out))

    print(f"\n{'='*64}\n  汇总:")
    print(f"  {'工况':<28} {'受照OBST':>9} {'子片':>6} {'最大热流':>9}")
    for s in summaries:
        print(f"  {s['tag']:<28} {s['lit_obst']:>9} {s['sub_faces']:>6} "
              f"{s['max_flux']:>9.0f}")


if __name__ == '__main__':
    main()

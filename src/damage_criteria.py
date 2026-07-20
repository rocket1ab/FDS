#!/usr/bin/env python3
"""
damage_criteria.py
==================
飞机内部设备/结构毁伤判据库（来自手写笔记转录）

核心判据（双重条件）
--------------------
某个部件被判定为"毁伤"，当且仅当其温度满足：
    温度 T(t) ≥ 临界温度 T_crit  且  持续时间 ≥ 耐受时间 τ_tol

也就是说：不是一超过临界温度就毁伤，而是要在临界温度以上"待够"耐受时间。
这比单一温度阈值更符合材料热失效的物理（热失效需要热量累积/时间积累）。

三类判据
--------
1. 设备类（equipment）：临界温度 + 耐受时间 + 失效温度(500°C 基底) + 失效机理
2. 结构材料类（structural）：临界温度 + 耐受时间 + 强度退化阈值
3. 接头/连接类（joints）：临界温度 + 失效判据描述

本模块被 generate_fds.py（用于决定监测哪些部件）和 damage_postprocess.py
（用于判定毁伤）共同 import。
"""

# ══════════════════════════════════════════════════════════════════════════════
# 第 1 类：机外/机体设备类毁伤判据
# 字段：临界温度(°C), 耐受时间(s), 失效温度(°C), 失效机理
# ══════════════════════════════════════════════════════════════════════════════
EQUIPMENT_CRITERIA = {
    '复合材料蒙皮':   dict(T_crit=350, tau_tol=90,  T_fail=500, mechanism='基体/介电破坏', abbr='SKIN'),
    '雷达罩':         dict(T_crit=200, tau_tol=45,  T_fail=500, mechanism='介电性能降级',  abbr='RADM'),
    '空速管':         dict(T_crit=400, tau_tol=30,  T_fail=500, mechanism='测量失准',      abbr='PITO'),
    '着陆灯组件':     dict(T_crit=300, tau_tol=60,  T_fail=500, mechanism='光学/电气失效', abbr='LAND'),
    # B-52H 机头段可燃内饰（对照图 U 类部件，与 FDS 材料一一对应）
    '座椅和头枕':     dict(T_crit=300, tau_tol=60,  T_fail=500, mechanism='软质内饰热失效', abbr='SEAT'),
    '风挡侧窗':       dict(T_crit=200, tau_tol=45,  T_fail=500, mechanism='透明件介电/光学失效', abbr='WINS'),
    '床垫':           dict(T_crit=180, tau_tol=120, T_fail=500, mechanism='纺织品热失效', abbr='BED'),
    '尼龙窗帘':       dict(T_crit=180, tau_tol=120, T_fail=500, mechanism='纺织品热失效', abbr='CURT'),
    '仪表台':         dict(T_crit=350, tau_tol=90,  T_fail=500, mechanism='复材面板强度退化', abbr='INST'),
    '机翼前缘除冰':   dict(T_crit=180, tau_tol=120, T_fail=500, mechanism='加热元件失效',  abbr='DEIC'),
    'VHF通信天线':    dict(T_crit=250, tau_tol=40,  T_fail=500, mechanism='通信中断',      abbr='VHFA'),
    '静电放电刷':     dict(T_crit=450, tau_tol=15,  T_fail=500, mechanism='放电能力丧失',  abbr='STAT'),
    'APU排气消音':    dict(T_crit=600, tau_tol=20,  T_fail=500, mechanism='结构软化',      abbr='APUE'),
    '飞行器导引灯':   dict(T_crit=220, tau_tol=75,  T_fail=500, mechanism='光学失效',      abbr='NAVL'),
    '火焰探测罐':     dict(T_crit=280, tau_tol=50,  T_fail=500, mechanism='探测失效',      abbr='FIRE'),
}

# ══════════════════════════════════════════════════════════════════════════════
# 第 2 类：结构材料类毁伤判据（强度退化）
# 字段：临界温度(°C), 耐受时间(s), 退化阈值(强度损失百分比)
# ══════════════════════════════════════════════════════════════════════════════
STRUCTURAL_CRITERIA = {
    '2024-T3铝合金':   dict(T_crit=180, tau_tol=300, degradation='强度退化>50%', abbr='AL2024'),
    '7075-T6铝合金':   dict(T_crit=160, tau_tol=240, degradation='强度退化>60%', abbr='AL7075'),
    'Ti-6Al-4V钛合金': dict(T_crit=550, tau_tol=600, degradation='强度退化>30%', abbr='TI64'),
    '石英纤维复材':    dict(T_crit=350, tau_tol=90,  degradation='强度退化>80%', abbr='QFRP'),
    '芳纶纤维束':      dict(T_crit=220, tau_tol=45,  degradation='强度退化>100%', abbr='ARAM'),
}

# ══════════════════════════════════════════════════════════════════════════════
# 第 3 类：接头/连接类毁伤判据
# 字段：临界温度(°C), 失效判据描述
# ══════════════════════════════════════════════════════════════════════════════
JOINT_CRITERIA = {
    '铆钉连接': dict(T_crit=200, criterion='剪切强度下降>40%', abbr='RIVT'),
    '螺栓连接': dict(T_crit=300, criterion='预紧力衰减>60%',   abbr='BOLT'),
    '胶接接头': dict(T_crit=150, criterion='剥离强度<1.5kN/m', abbr='ADHE'),
    '焊接接头': dict(T_crit=400, criterion='疲劳寿命降至10³ cycles', abbr='WELD'),
}

# ══════════════════════════════════════════════════════════════════════════════
# FDS 材料 → 毁伤判据的映射
# ──────────────────────────────────────────────────────────────────────────────
# 模型中的可燃/结构材料对应到哪条毁伤判据。
# 注：模型用的是材料（聚氨酯泡沫等），这里映射到最贴近的判据类别。
# ══════════════════════════════════════════════════════════════════════════════
MATL_TO_CRITERIA = {
    # 可燃内饰材料 → B-52H 对照图部件名（crit_key 用于报告与后处理显示）
    '聚氨酯泡沫':       ('equipment',  '座椅和头枕'),    # U6
    '丙烯酸塑料':       ('equipment',  '风挡侧窗'),      # 25 mm 侧窗/风挡
    '尼龙织物_床垫':    ('equipment',  '床垫'),          # U5
    '尼龙织物_窗帘3mm': ('equipment',  '尼龙窗帘'),      # U1/U2（单 m 变体）
    '尼龙织物_窗帘3mmm':('equipment',  '尼龙窗帘'),      # U1/U2（Separated_merge_v2 双 m）
    '环氧玻璃纤维':     ('equipment',  '仪表台'),        # U4 FR-4
    'E-玻璃纤维':       ('equipment',  '雷达罩'),        # 机头雷达罩（v2 新增）
    # 结构铝合金 → 结构材料判据
    '铝合金2024':       ('structural', '2024-T3铝合金'),
    '铝合金5052':       ('structural', '2024-T3铝合金'),
    '铝合金7075':       ('structural', '7075-T6铝合金'),
    '铝合金7075_氧气瓶': ('structural', '7075-T6铝合金'),
}

# B-52H 对照图部件名（铝合金结构件，用于报告/后处理显示）
ALUMINUM_PART_LABEL = {
    '铝合金2024': '蒙皮',
    '铝合金5052': '通风管 (C2)',
    '铝合金7075': '隔框/隔板 (C1)',
    '铝合金7075_氧气瓶': '氧气瓶 (U3)',
}

# FDS DEVC ID 缩写（铝合金探针）
ALUMINUM_SURF_ABBR = {
    '铝合金2024': 'AL2024',
    '铝合金5052': 'AL5052',
    '铝合金7075': 'AL7075',
    '铝合金7075_氧气瓶': 'O2TANK',
}

# 各铝合金 SURF 监测探针数量上限（氧气瓶优先）
ALUMINUM_MONITOR_TOP = {
    '铝合金7075_氧气瓶': 3,
    '铝合金7075': 2,
    '铝合金2024': 2,
    '铝合金5052': 1,
}


# 可燃内饰部件显示名
INTERIOR_PART_LABEL = {
    '聚氨酯泡沫': '座椅和头枕 (U6)',
    '丙烯酸塑料': '风挡侧窗',
    '尼龙织物_床垫': '床垫 (U5)',
    '尼龙织物_窗帘3mm': '尼龙窗帘 (U1/U2)',
    '尼龙织物_窗帘3mmm': '尼龙窗帘 (U1/U2)',
    '环氧玻璃纤维': '仪表台 (U4)',
    'E-玻璃纤维': '雷达罩',
}


def part_label_for_matl(matl_name):
    """材料名 → 报告用部件显示名。"""
    return ALUMINUM_PART_LABEL.get(matl_name) or INTERIOR_PART_LABEL.get(matl_name)


def get_criterion(category, name):
    """统一查询接口。category ∈ {'equipment','structural','joint'}。"""
    if category == 'equipment':
        return EQUIPMENT_CRITERIA.get(name)
    if category == 'structural':
        return STRUCTURAL_CRITERIA.get(name)
    if category == 'joint':
        return JOINT_CRITERIA.get(name)
    return None


def lookup_by_matl(matl_name):
    """由 FDS 材料名查到 (category, criterion_name, criterion_dict)。"""
    mapping = MATL_TO_CRITERIA.get(matl_name)
    if mapping is None:
        return None
    category, crit_name = mapping
    crit = get_criterion(category, crit_name)
    return category, crit_name, crit


def evaluate_damage(time, temp, T_crit, tau_tol):
    """
    对一条温度时程做双重判据评估。

    参数
    ----
    time : 时间序列 (s)
    temp : 对应温度序列 (°C)
    T_crit : 临界温度 (°C)
    tau_tol : 耐受时间 (s)

    返回 dict(
        T_max          峰值温度
        t_first_exceed 首次超过 T_crit 的时刻（None=从未超过）
        cum_time_above 累计在 T_crit 以上的时间（s）
        max_continuous 在 T_crit 以上的最长连续时间（s）
        damaged        是否毁伤（max_continuous >= tau_tol）
        t_damage       毁伤判定时刻（持续达到 tau_tol 的时刻；None=未毁伤）
        margin         裕度 = max_continuous - tau_tol（正=毁伤，负=安全余量）
    )

    判据：温度持续 ≥ T_crit 达 tau_tol 秒 → 毁伤。
    用"最长连续时间"而非"累计时间"，因为热失效需要连续受热
    （中途冷却会部分恢复）；但也同时报告累计时间供参考。
    """
    import numpy as np
    time = np.asarray(time, dtype=float)
    temp = np.asarray(temp, dtype=float)
    above = temp >= T_crit

    T_max = float(temp.max()) if len(temp) else float('nan')
    if not above.any():
        return dict(T_max=T_max, t_first_exceed=None, cum_time_above=0.0,
                    max_continuous=0.0, damaged=False, t_damage=None,
                    margin=-tau_tol)

    t_first = float(time[np.argmax(above)])

    # 累计时间（梯形，按相邻采样间隔加权）
    dt = np.diff(time, prepend=time[0])
    cum_above = float(dt[above].sum())

    # 最长连续时间 + 毁伤时刻
    max_cont = 0.0
    cur_start = None
    t_damage = None
    for i in range(len(time)):
        if above[i]:
            if cur_start is None:
                cur_start = time[i]
            cont = time[i] - cur_start
            if cont > max_cont:
                max_cont = cont
            if t_damage is None and cont >= tau_tol:
                t_damage = float(time[i])
        else:
            cur_start = None

    damaged = max_cont >= tau_tol
    return dict(T_max=T_max, t_first_exceed=t_first, cum_time_above=cum_above,
                max_continuous=float(max_cont), damaged=bool(damaged),
                t_damage=t_damage, margin=float(max_cont - tau_tol))


def all_criteria_table():
    """返回所有判据的扁平列表，供报告/汇总使用。"""
    rows = []
    for name, c in EQUIPMENT_CRITERIA.items():
        rows.append(dict(category='设备', name=name, T_crit=c['T_crit'],
                         tau_tol=c['tau_tol'], extra=c['mechanism'], abbr=c['abbr']))
    for name, c in STRUCTURAL_CRITERIA.items():
        rows.append(dict(category='结构', name=name, T_crit=c['T_crit'],
                         tau_tol=c['tau_tol'], extra=c['degradation'], abbr=c['abbr']))
    for name, c in JOINT_CRITERIA.items():
        rows.append(dict(category='接头', name=name, T_crit=c['T_crit'],
                         tau_tol=None, extra=c['criterion'], abbr=c['abbr']))
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# §X  英文名映射（供绘图用，避免 matplotlib 中文字形缺失乱码）
# ══════════════════════════════════════════════════════════════════════════════
# 判据键(中文) → 英文显示名
CRIT_KEY_EN = {
    '复合材料蒙皮': 'Composite skin', '雷达罩': 'Radome', '空速管': 'Pitot tube',
    '着陆灯组件': 'Landing light', '机翼前缘除冰': 'Wing de-ice',
    '座椅和头枕': 'Seat/headrest', '座椅和头枕 (U6)': 'Seat/headrest (U6)',
    '风挡侧窗': 'Windshield side window',
    '床垫': 'Mattress', '床垫 (U5)': 'Mattress (U5)',
    '尼龙窗帘': 'Nylon curtain', '尼龙窗帘 (U1/U2)': 'Nylon curtain (U1/U2)',
    '仪表台': 'Instrument panel', '仪表台 (U4)': 'Instrument panel (U4)',
    'VHF通信天线': 'VHF antenna', '静电放电刷': 'Static discharger',
    'APU排气消音': 'APU exhaust', '飞行器导引灯': 'Nav light',
    '火焰探测罐': 'Flame detector',
    '2024-T3铝合金': 'Al 2024-T3', '7075-T6铝合金': 'Al 7075-T6',
    '蒙皮': 'Skin (Al2024)', '通风管 (C2)': 'Duct (Al5052)',
    '隔框/隔板 (C1)': 'Frame (Al7075)', '氧气瓶 (U3)': 'O2 tank (Al7075)',
    'Ti-6Al-4V钛合金': 'Ti-6Al-4V', '石英纤维复材': 'Quartz FRP',
    '芳纶纤维束': 'Aramid fiber',
    '铆钉连接': 'Rivet joint', '螺栓连接': 'Bolt joint',
    '胶接接头': 'Bonded joint', '焊接接头': 'Welded joint',
}
# FDS 材料名(中文) → 英文显示名
MATERIAL_EN = {
    '聚氨酯泡沫': 'PU foam', '丙烯酸塑料': 'Acrylic', '尼龙织物_床垫': 'Nylon mattress',
    '尼龙织物_ 床垫': 'Nylon mattress', '尼龙织物_窗帘3mm': 'Nylon curtain',
    '尼龙织物_窗帘3mmm': 'Nylon curtain',
    '环氧玻璃纤维': 'Epoxy GFRP', 'E-玻璃纤维': 'E-glass FRP', '铝合金2024': 'Al 2024',
    '铝合金7075': 'Al 7075', '铝合金7075_氧气瓶': 'Al 7075 (O2 tank)',
}


def crit_key_en(key):
    """判据键 → 英文名（缺失则拆分括号后缀再查表）。"""
    if key in CRIT_KEY_EN:
        return CRIT_KEY_EN[key]
    # e.g. "座椅和头枕 (U6)" → base "座椅和头枕" + suffix " (U6)"
    if ' (' in key and key.endswith(')'):
        base, _, suffix = key.partition(' (')
        suffix = f' ({suffix}'
        if base in CRIT_KEY_EN:
            en = CRIT_KEY_EN[base]
            # keep U-code suffix for traceability
            if suffix.strip(' ()') and '(' not in en:
                return f'{en} {suffix}'
            return en
    for tbl in (EQUIPMENT_CRITERIA, STRUCTURAL_CRITERIA, JOINT_CRITERIA):
        if key in tbl:
            return tbl[key].get('abbr', key)
    return key


def material_en(mat):
    """材料名 → 英文名（缺失则清洗为 ASCII）。"""
    if mat in MATERIAL_EN:
        return MATERIAL_EN[mat]
    import re as _re
    cleaned = _re.sub(r'[^A-Za-z0-9_.\- ]', '', mat).strip()
    return cleaned or 'material'


if __name__ == '__main__':
    # 自检：打印所有判据 + 演示双重判据评估
    print("="*70)
    print("飞机毁伤判据库自检")
    print("="*70)
    for r in all_criteria_table():
        tau = f"{r['tau_tol']}s" if r['tau_tol'] else "—"
        print(f"  [{r['category']}] {r['name']:<16} T_crit={r['T_crit']}°C "
              f"耐受={tau:<6} {r['extra']}")

    print("\n双重判据演示（雷达罩 T_crit=200°C, 耐受 45s）:")
    import numpy as np
    t = np.arange(0, 100, 1.0)
    # 模拟：温度升到 250°C 持续 60s（>45s 耐受 → 应毁伤）
    temp = np.where((t >= 20) & (t <= 80), 250., 20.)
    res = evaluate_damage(t, temp, 200, 45)
    print(f"  峰值温度: {res['T_max']:.0f}°C")
    print(f"  首次超临界: t={res['t_first_exceed']:.0f}s")
    print(f"  最长连续超临界: {res['max_continuous']:.0f}s")
    print(f"  毁伤判定: {'是' if res['damaged'] else '否'}"
          f"（裕度 {res['margin']:+.0f}s）")
    print(f"  毁伤时刻: t={res['t_damage']:.0f}s" if res['t_damage'] else "  未毁伤")

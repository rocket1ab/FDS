# Q400 表格近似 HRRPUA 与 BURN_AWAY 单因素对照

## 案例定义

新案例：

`Q0400_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRtable_thickness_audit_BAtrue_v1`

直接对照：

`Q0400_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRtable_thickness_audit_v1`

两者均采用 Q=400 J/cm2、W=100 kt、az=270 deg、el=15 deg、T_END=1500 s 和
修正后的入射面光冲量归一化。新案例唯一物理改动是对具有正 HRRPUA 的实际可燃
SURF 设置 `BURN_AWAY=.TRUE.`。

FDS 要求可烧蚀 `OBST` 显式给出 `BULK_DENSITY`，且零体积薄片不能进行质量耗尽
计算。因此生成器从各 `MATL` 的 `DENSITY` 继承体积密度，并仅对相应可燃
`OBST` 写入 `BULK_DENSITY`；零厚度维度按既有体素流程扩展为 0.01 m。这是启用
`BURN_AWAY` 所需的数值表达，不修改材料密度或审查后的 SURF 热学厚度。

## HRRPUA

| 对象 | HRRPUA (kW/m2) |
|---|---:|
| RADM | 75 |
| WINS | 250 |
| BED | 400 |
| CURT | 400 |
| U4 | 350 |
| SEAT | 450 |
| H6 | 200 |
| H7 | 180 |
| H1-H5 | 0，不可燃 |

## 探针与判据

继续使用各对象现有的多位置冗余 `WALL TEMPERATURE` 探针和边界输出。评估脚本
保留每个探针的有限值历史、峰值和最后有效时间；表面烧蚀后的缺失值不填零，也不
解释为冷却。探针末端失效可作为表面消失的辅助证据，但不替代 PDF 规定的温度与
持续时间判据，气相温度也不替代壁面温度。

该案例只用于评价 `BURN_AWAY` 对燃料耗尽、持续燃烧和温度历程的影响，不与
`BURN_AWAY=.FALSE.` 案例混合形成光冲量阈值。

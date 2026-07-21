# H1-H7 v4 current parameter inventory

This inventory is extracted from the effective `cases_legacy_stable` FDS files
running on 2026-07-21. It supersedes queue metadata and older reports wherever
they differ.

## 1. Case matrix and runtime allocation

| Case Q (J/cm2) | Yield (kt) | Azimuth (deg) | Elevation (deg) | T_END (s) | Peak local EXTERNAL_FLUX (kW/m2) | Peak local integrated fluence (J/cm2) | Runtime queue |
|---:|---:|---:|---:|---:|---:|---:|---|
| 50 | 100 | 270 | 15 | 1500 | 219 | 14.46 | node05, first |
| 100 | 100 | 270 | 15 | 1500 | 437 | 28.86 | node04, first |
| 200 | 100 | 270 | 15 | 1500 | 874 | 57.72 | node05, second |
| 300 | 100 | 270 | 15 | 1500 | 1312 | 86.64 | node04, second |
| 400 | 100 | 270 | 15 | 1500 | 1749 | 115.50 | node05, third |

The campaign Q value is the incident plane/source fluence. The local applied
surface value is reduced by face projection, voxel visibility and transmission,
then quantized to integer kW/m2. It must not be confused with the maximum local
integrated fluence in the table. The current direction vector produced by the
code is `(-0.965926, 0, 0.258819)`.

## 2. External-flux model

The effective boundary condition is

`q_external(x,t) = EXTERNAL_FLUX(x) * NUCLEAR_RAMP(t)`.

Illuminated geometry is split into non-overlapping OBST records and assigned
with `SURF_ID6`. There are no generated overlay VENT records. Each case has 24
positive integer flux levels. Their ranges are 9-219, 17-437, 35-874, 52-1312
and 70-1749 kW/m2 for Q50 through Q400 respectively. Unilluminated faces retain
their base surface with no `EXTERNAL_FLUX`.

`NUCLEAR_RAMP` has a trapezoidal integral of 0.660398 s, peaks at F=1 at
0.303431 s and returns to zero by 4.758339 s (with a final zero point at
4.763072 s).

| T (s) | F | T (s) | F |
|---:|---:|---:|---:|
| 0.000000 | 0.000 | 0.030343 | 0.026 |
| 0.060686 | 0.110 | 0.091028 | 0.230 |
| 0.121371 | 0.380 | 0.151715 | 0.565 |
| 0.182057 | 0.735 | 0.212403 | 0.855 |
| 0.242745 | 0.945 | 0.273088 | 0.980 |
| 0.303431 | 1.000 | 0.364116 | 0.935 |
| 0.424802 | 0.795 | 0.485488 | 0.630 |
| 0.546174 | 0.520 | 0.606861 | 0.430 |
| 0.667547 | 0.366 | 0.728233 | 0.320 |
| 0.788918 | 0.280 | 0.849604 | 0.245 |
| 0.910291 | 0.218 | 0.970976 | 0.195 |
| 1.031664 | 0.175 | 1.092349 | 0.158 |
| 1.153035 | 0.140 | 1.213722 | 0.126 |
| 1.365435 | 0.098 | 1.517152 | 0.082 |
| 1.668866 | 0.067 | 1.820583 | 0.061 |
| 1.972298 | 0.052 | 2.124011 | 0.046 |
| 2.427442 | 0.037 | 2.730873 | 0.031 |
| 3.034303 | 0.029 | 3.337733 | 0.027 |
| 3.641164 | 0.025 | 3.944594 | 0.024 |
| 4.248025 | 0.023 | 4.758339 | 0.000 |
| 4.763072 | 0.000 | | |

## 3. FDS and numerical settings

| Item | Effective value |
|---|---|
| FDS version | 6.9.0 |
| Simulation horizon | 1500 s |
| MPI processes | 32 |
| Mesh count | 32, one assigned to each MPI process |
| Total cells | 395,712 |
| Domain | X=-0.3 to 10.1 m; Y=-1.9 to 1.7 m; Z=-2.2 to 2.6 m |
| Main cabin cell size | 0.10 x 0.10 x 0.10 m |
| Aft mesh cell size | approximately 0.0528 x 0.05 x 0.05 m |
| OBST count | 5,363 |
| VENT count | 2, both `OPEN` on ZMAX |
| Density clipping | `MINIMUM_DENSITY=0.01`, `MAXIMUM_DENSITY=10000` kg/m3 |
| Restart interval | `DT_RESTART=300 s` |
| Smoke3D interval | `DT_SL3D=0.25 s` |
| Explicit DT/CFL/PRES/MISC | Not specified; FDS defaults apply |
| Burn-away | No `BURN_AWAY=.TRUE.`; effective false throughout |

Outputs comprise three slices (`TEMPERATURE` at Y=0, `HRRPUV` at Y=0,
`TEMPERATURE` at Z=0.8), three boundary files (`WALL TEMPERATURE`, `NET HEAT
FLUX`, `BURNING RATE`), 153 wall-temperature probes, 153 net-heat-flux probes
and one whole-domain HRR device. `DT_DEVC` is not explicitly set; the current
1500 s files use the FDS default output scheduling.

## 4. Gas-phase combustion

| Parameter | Value |
|---|---:|
| Reaction ID | `SIMPLE_BURN` |
| Fuel | `SFUEL` |
| Empirical formula | C1 H1.7 O0.3 N0.08 |
| Heat of combustion | 20,000 kJ/kg |
| CO yield | 0.03 kg/kg |
| Soot yield | 0.10 kg/kg |
| Radiative fraction | 0.40 |

A separate species record named `SFPE POLYURETHANE_GM27_fuel` with formula
C1.0H1.7O0.3N0.08 is present, but the active REAC names `SFUEL`. FDS accepts
the input with a warning. The surface burning ramp `Q_RAMP` is F=0 at 0 s and
F=1 at 3 s; because there is no later point, F remains 1 after 3 s.

## 5. Solid material properties

FDS units are kg/m3 for density, kJ/(kg K) for specific heat, W/(m K) for
conductivity and dimensionless for emissivity.

| MATL | Physical material | Density | Specific heat | Conductivity | Emissivity |
|---|---|---:|---:|---:|---:|
| EBLXW | E-glass fiber/radome | 2540 | 1.00 | 0.35 | 0.90 |
| BXSSL | PMMA/acrylic | 1190 | 1.46 | 0.19 | 0.90 |
| NLZW | Nylon fabric | 1140 | 1.70 | 0.25 | 0.90 |
| HYBLXW | Epoxy glass fiber/U4 | 2540 | 1.00 | 0.35 | 0.90 |
| JAZPM | Polyurethane foam | 35 | 1.40 | 0.03 | 0.90 |
| LHJ2024 | Aluminium 2024 | 2780 | 0.875 | 60 | 0.90 |
| LHJ5052 | Aluminium 5052 | 2680 | 0.88 | 70 | 0.90 |
| LHJ7075 | Aluminium 7075 | 2810 | 0.96 | 65 | 0.90 |
| LHJ6061 | Aluminium 6061 | 2700 | 0.896 | 167 | 0.90 |
| PVCSL | PVC | 1449 | 0.84 | 0.19 | 0.90 |
| CRXJ | CR rubber | 1500 | 1.12 | 0.19 | 0.90 |

No current MATL record contains Arrhenius A, activation energy E, reaction
order, heat of reaction, residue fraction, gaseous yield or bulk density. The
current runs therefore do **not** use an A/E pyrolysis model.

## 6. Effective surface and burning parameters

| Group | Surface/material | Thickness | Ignition temperature | HRRPUA | Q ramp | Burn-away |
|---|---|---:|---:|---:|---|---|
| RADM | E-glass fiber | 120 mm | 400 C | 75 kW/m2 | Immediate/default | False/default |
| WINS | PMMA | 75 mm | 250 C | 250 kW/m2 | Immediate/default | False/default |
| BED | Nylon mattress | 120 mm | 250 C | 180 kW/m2 | 0 to 1 over 3 s | False |
| CURT | Nylon curtain | 30 mm | 250 C | 180 kW/m2 | 0 to 1 over 3 s | False |
| U4 | Epoxy glass fiber | 30 mm | 350 C | 100 kW/m2 | 0 to 1 over 3 s | False/default |
| SEAT | Polyurethane foam | 150 mm | 250 C | 200 kW/m2 | 0 to 1 over 3 s | False |
| AL2024 | Aluminium 2024 | 2.0 mm | None | 0 | None | False/default |
| AL5052 | Aluminium 5052 | 1.5 mm | None | 0 | None | False/default |
| AL7075 | Aluminium 7075 | 3.0 mm | None | 0 | None | False/default |
| O2TANK | Aluminium 7075 | 5.0 mm | None | 0 | None | False/default |
| H1 | Aluminium 6061 | 3.0 mm | None | 0 | None | False/default |
| H2 | Aluminium 6061 | 3.0 mm | None | 0 | None | False/default |
| H3 | Aluminium 6061 | 3.0 mm | None | 0 | None | False/default |
| H4 | Aluminium 6061 | 3.0 mm | None | 0 | None | False/default |
| H5 | Aluminium 6061 | 3.0 mm | None | 0 | None | False/default |
| H6 | PVC | 1.0 mm | 468.6 C | 200 kW/m2 | 0 to 1 over 3 s | False/default |
| H7 | CR rubber | 2.0 mm | 410 C | 180 kW/m2 | 0 to 1 over 3 s | False/default |

Because burn-away is false and Q_RAMP remains at 1, an ignited prescribed-HRRPUA
surface has no finite fuel depletion mechanism in the current model.

## 7. Probe inventory

| Group | Temperature probes | Heat-flux probes |
|---|---:|---:|
| RADM | 10 | 10 |
| WINS | 10 | 10 |
| BED | 8 | 8 |
| CURT | 10 | 10 |
| U4 | 6 | 6 |
| SEAT | 10 | 10 |
| AL2024 | 10 | 10 |
| AL5052 | 10 | 10 |
| AL7075 | 10 | 10 |
| O2TANK | 10 | 10 |
| H1 | 7 | 7 |
| H2 | 10 | 10 |
| H3 | 14 | 14 |
| H4 | 10 | 10 |
| H5 | 6 | 6 |
| H6 | 8 | 8 |
| H7 | 4 | 4 |

Damage evaluation uses the time-wise maximum envelope over all valid wall
temperature probes in each group.

## 8. Damage thresholds

Each cell is temperature in C followed by required continuous duration in s.

| Group | Mild | Moderate | Severe |
|---|---:|---:|---:|
| RADM | 150 / 300 | 250 / 180 | 400 / 180 |
| WINS | 120 / 60 | 200 / 45 | 250 / 8 |
| BED | 200 / 60 | 250 / 90 | 500 / 5 |
| CURT | 200 / 60 | 250 / 90 | 500 / 5 |
| U4 | 120 / 300 | 250 / 180 | 400 / 5 |
| SEAT | 200 / 60 | 300 / 90 | 500 / 5 |
| AL2024 | 120 / 600 | 250 / 300 | 400 / 60 |
| AL5052 | 120 / 600 | 250 / 300 | 400 / 60 |
| AL7075 | 120 / 600 | 200 / 240 | 400 / 60 |
| O2TANK | 120 / 600 | 200 / 240 | 400 / 60 |
| H1 | 120 / 300 | 250 / 180 | 400 / 5 |
| H2 | 120 / 300 | 250 / 180 | 400 / 5 |
| H3 | 120 / 300 | 250 / 180 | 400 / 5 |
| H4 | 120 / 300 | 250 / 180 | 400 / 5 |
| H5 | 100 / 60 | 150 / 600 | 200 / 180 |
| H6 | 120 / 1200 | 200 / 600 | 400 / 180 |
| H7 | 120 / 300 | 250 / 180 | 400 / 5 |


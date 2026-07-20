# Aircraft voxel ignition and damage workflow (2026-07-20 H1-H7)

This folder is isolated from the 20260711 and 20260719 projects.

## Fixed scenario matrix

All cases use 100 kt, azimuth 270 deg, elevation 15 deg, `T_END=1500 s`,
32 MPI processes, and the archived BA0 prescribed-ignition/HRRPUA physics.
The fluence values are 50, 100, 200, 300, and 400 J/cm2.

Node allocation:

| Node | Sequential queue |
|---|---|
| node03 | Q50, Q200, Q400 |
| node04 | Q100, Q300 |

Each queue waits until no `fds` process remains and the one-minute load leaves
capacity for 32 MPI ranks. Only one new case runs on a node at a time. Before
the first formal case, the queue runs a 0.01 s FDS preflight and checks both
the completion marker and the log for setup errors.

## Updated equipment

| Equipment | Surface material | Thickness |
|---|---|---:|
| H1-H5 | Aluminium 6061-T6 | 3 mm |
| H6 | PVC | 1 mm |
| H7 | CR rubber | 2 mm |
| U4 | Epoxy glass fibre, inherited from U04 | 30 mm |

The source value `SPECIFIC_HEAT=896.0` for 6061 is converted from J/(kg K) to
the FDS input unit and written as `0.896 kJ/(kg K)`. H6 uses 468.6 C and
200 kW/m2; H7 uses 410 C and 180 kW/m2. The A/E values from the source table
are retained as source evidence but are not active in these BA0 prescribed
HRRPUA cases, preventing two solid-fuel models from being mixed.

## Monitoring and assessment

Every case contains redundant wall-temperature and net-heat-flux probes for
all 17 evaluation groups. Post-processing constructs a time-varying maximum
temperature envelope from all valid probes, so a missing or future burned-away
probe can be replaced by another probe without losing the group history.

After each FDS process exits, `src/assess_results.py` writes equipment damage,
system damage-tree propagation, aircraft damage, and the severe-damage ratio.
`threshold_status.json` records the current threshold bracket.

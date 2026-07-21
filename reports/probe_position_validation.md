# Probe Position Validation

Case: `Q0100_W0100_az270_el15_H1H7_v5_Qnorm`

## Result

- Position validation: **FAIL**
- Temperature probes: **153**
- Co-located net-heat-flux probes: **153**
- Validated against current FDS and voxel exposed-face records: **147/153**
- Probe coordinates are intentionally 0.035 m outside the selected voxel face; `IOR` points to that boundary.

## Per-group coverage

| Group | Component | Material | WT probes | Unique positions | Candidate faces | Directly irradiated | Status |
|---|---|---|---:|---:|---:|---:|---|
| RADM | Radome | Fiberglass | 10 | 10 | 386 | 10 | PASS |
| WINS | Windows | PMMA | 10 | 10 | 213 | 10 | PASS |
| BED | Mattress | Nylon | 8 | 8 | 99 | 8 | PASS |
| CURT | Curtain | Nylon | 10 | 10 | 267 | 10 | PASS |
| U4 | U4 equipment | Legacy U04 material | 6 | 6 | 0 | 0 | PASS |
| SEAT | Seats | Polyurethane foam | 10 | 10 | 92 | 4 | PASS |
| AL2024 | Aircraft skin | Aluminium 2024 | 10 | 10 | 674 | 5 | PASS |
| AL5052 | Duct | Aluminium 5052 | 10 | 10 | 0 | 0 | PASS |
| AL7075 | Frame | Aluminium 7075 | 10 | 10 | 121 | 3 | PASS |
| O2TANK | Oxygen tank | Aluminium 7075 | 10 | 10 | 10 | 6 | FAIL |
| H1 | Navigation subsystem | Aluminium 6061, 3 mm | 7 | 7 | 5 | 5 | FAIL |
| H2 | Mission subsystem | Aluminium 6061, 3 mm | 10 | 10 | 37 | 8 | FAIL |
| H3 | Display subsystem | Aluminium 6061, 3 mm | 14 | 14 | 0 | 0 | PASS |
| H4 | Communication subsystem | Aluminium 6061, 3 mm | 10 | 10 | 4 | 4 | PASS |
| H5 | Battery | Aluminium 6061, 3 mm | 6 | 6 | 4 | 3 | PASS |
| H6 | Power transmission | PVC, 1 mm | 8 | 8 | 0 | 0 | PASS |
| H7 | Flight-control subsystem | CR rubber, 2 mm | 4 | 4 | 0 | 0 | FAIL |

## Suspect probes

These probes are present in the FDS file and have a co-located heat-flux pair, but their requested location is more than one 0.1 m grid cell from the intended oriented material face:

- `P_O2TANK_02_WT`: nearest intended face = 0.165 m
- `P_O2TANK_05_WT`: nearest intended face = 0.165 m
- `P_H1_09_WT`: nearest intended face = 0.115 m
- `P_H2_08_WT`: nearest intended face = 0.135 m
- `P_H2_09_WT`: nearest intended face = 0.165 m
- `P_H7_02_WT`: nearest intended face = 0.115 m

## Interpretation

The temperature reported for a material is the maximum among its redundant WALL TEMPERATURE probes. It is a monitored maximum, not a continuous maximum over every FDS surface cell. The probes deliberately combine high-flux locations with spatially separated locations, and each has a co-located NET HEAT FLUX probe.

Groups with zero directly irradiated probes are geometrically shielded for the current azimuth/elevation; their probes remain useful for secondary heating and fire exposure.

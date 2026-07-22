# FDS stability rerun record (2026-07-21)

## Initial finding, superseded by completed reference

The archived Q400 case was not a completed stable run. It had no
`STOP: FDS completed successfully` record and was externally stopped at
193.18 s. Immediately before termination, the maximum divergence in the aft
meshes had already reached approximately 67 to 78. The H1-H7 v2 cases failed
at 176.87 to 179.09 s with the same aft-mesh divergence pattern. The evidence
therefore does not support a geometry-only regression in the updated model.

The later supplied `Q50_W100_el15_BA0_RF40_B1` reference completed normally at
900 s while retaining the same global `Q_RAMP`. This disproves the initial
hypothesis that `Q_RAMP` was the primary cause of the new failure.

The completed reference has 4301 OBST records, two domain VENT records and 83
devices. Its external flux is attached directly to split obstacles with
`SURF_ID6`. The failed H1-H7 v2 model has 4168 original OBST records plus 1912
generated flux-overlay VENT records and 307 devices. The dominant untested
solver difference is therefore the overlay VENT representation.

## Stable v3 diagnostic

The stable cases are stored under `cases_stable` and do not overwrite v2.

1. Peak HRRPUA, ignition temperatures, material properties, external flux,
   fluence, yield and incident angles remain unchanged.
2. Combustible surfaces use `TAU_Q=10.0 s` as a diagnostic alternative to the
   global `RAMP_Q`; this is not retained in the legacy baseline.
3. `TIME` uses `DT=0.002 s`.
4. `MISC` uses `CFL_MAX=0.5` and `CHECK_HT=.TRUE.`.
5. Density clipping and up to 100 pressure iterations are enabled.
6. `BURN_AWAY` remains false, avoiding geometry changes during this threshold
   campaign.

FDS 6.9.0 requires `CFL_MAX` on `MISC`, not `TIME`. The remote preflight now
changes only `T_END`, preserving and validating all numerical controls.

## Stable v4 legacy baseline

The v4 cases retain the updated H1-H7 geometry, materials, probes and flux
magnitudes, but remove all 1912 generated VF overlay vents. Illuminated
surfaces are represented by split OBST records and `SURF_ID6`, matching the
completed reference method. Multi-face equipment is partitioned into
non-overlapping Cartesian sub-blocks before face properties are assigned.

The first v4 comparison deliberately uses the completed reference controls:
`RADIATIVE_FRACTION=0.40`, `CLIP`, the original `Q_RAMP`,
`BURN_AWAY=FALSE` and `T_END=1500 s`. This isolates the updated geometry and
flux-boundary representation from unrelated numerical changes.

## Queue allocation

Node 03 was not used because its load was approximately 103 and SSH was
intermittent. The idle node 05 temporarily took its queue.

| Node | Sequential cases |
|---|---|
| node05 | Q50, Q200, Q400 J/cm2 |
| node04 | Q100, Q300 J/cm2 |

Each node runs one 32-process FDS case at a time. A case is assessed only when
the log contains `STOP: FDS completed successfully` and does not contain
`Numerical Instability`.

Both node preflights passed on 2026-07-21. The formal RF=0.40 queues then
started with Q100 on node04 and Q50 on node05, each using 32 FDS processes.

## Automatic threshold search (2026-07-22)

An independent threshold campaign uses the completed non-all-severe Q300 case
as its initial failed lower bound and keeps the validated geometry, 100 kt yield,
azimuth 270 deg, elevation 15 deg, materials, probes, combustion inputs and
damage criteria fixed. It starts with Q400 on node04. Once an all-severe upper
bound exists, it bisects fluence to a 5 J/cm2 bracket. If Q400 is not all-severe,
the controller first raises only fluence by a factor of 1.5 (capped at
1200 J/cm2) until a valid upper bound is found. Existing baseline queues remain
unchanged and threshold cases use separate directories and CHIDs.

## BED-only HRRPUA sensitivity (2026-07-22)

The corrected Q400 threshold input shows BED probe peaks up to about 691 C but
less than the required continuous 500 C by 5 s. The baseline treats the entire
120 mm mattress as solid nylon (density 1140 kg/m3), so changing density or
thickness without measured mattress mass and layer construction would not be
defensible. A separate single-factor bounding case therefore changes only BED
HRRPUA from 180 to 790 kW/m2. Q, yield, angle, geometry, material thermal
properties, ignition temperature, BURN_AWAY, probes and criteria are unchanged.
The 790 kW/m2 value is a cone-calorimeter upper-bound sensitivity for neat
Nylon-6 at 35 kW/m2 exposure and is not a replacement for specimen data.
Successful startup is not yet proof of stability: the v4 baseline must pass the
previous 176.87 to 179.09 s failure window before the overlay-VENT hypothesis
is supported, and normal completion at 1500 s remains the final acceptance
criterion. The required production horizon was extended from the completed
reference's 900 s to 1500 s before the formal queues were restarted.

## Legacy-flux retirement and Q-normalized restart

The v4 queues were stopped on 2026-07-21 after identifying a physical input
normalization error. The old rule scaled a Q400 reference peak of 1749 kW/m2
linearly, so its Q100 maximum local fluence was only 28.86 J/cm2 for the
0.660398 s pulse integral. Numerical stability of those runs does not correct
that mismatch, and their outputs are excluded from threshold conclusions.

The v5 Q-normalized campaign computes the incident-plane peak as
`E0 = 10 Q / integral(F dt)`. Geometry, visibility factors, materials, damage
criteria, combustion parameters, RF=0.40, `BURN_AWAY=FALSE` and the 1500 s
horizon are unchanged. Corrected local maxima are 48.539, 97.145, 194.223,
291.368 and 388.512 J/cm2 for nominal Q50, Q100, Q200, Q300 and Q400.

Node04 passed preflight and started corrected Q300. Node05 passed preflight and
started corrected Q50, followed by Q200 and Q400. The already-running corrected
Q100 remains on node01. No legacy v4 FDS process remains on node04 or node05.

## Probe geometry QA and v6 correction

Geometry QA compared every WT/HF pair with the current FDS DEVC records and
the oriented material face after 0.1 m grid snapping. The v5 registry contained
153 paired WT/HF locations; 147 passed and six were more than one cell from the
intended face: O2TANK 02/05, H1 09, H2 08/09 and H7 02.

Live v5 assessment now excludes those six IDs while retaining the remaining
valid redundant probes. The separate `cases_probe_corrected` v6 campaign moves
only those six WT/HF pairs to a 0.035 m offset from the intended material face.
All five Q50-Q400 v6 inputs pass 153/153 geometry QA. External flux, geometry,
materials, pulse, combustion and damage criteria are unchanged. Existing v5
runs were not modified or restarted. `BNDF WALL TEMPERATURE` and
`BNDF NET HEAT FLUX` remain enabled, providing a full-surface field cross-check
after each run completes.
## Q100 adaptive campaign: measured upper HRRPUA and geometry sensitivities

The corrected Q100 v5 case remains an unchanged control. Three independent
same-fluence variants were generated in `cases_adaptive`; each changes one
factor only and retains Q=100 J/cm2, W=100 kt and the original damage criteria.

Run order on the first suitable idle node is:

1. `Q0100_W0100_az090_el75_H1H7_v5_Qnorm_adapt_angle`: DDA-selected
   angle sensitivity, az=90 deg and el=75 deg. The scan exposes 13 monitored
   groups and 9 currently underperforming target groups. It improves direct
   exposure of H4, H7 and AL5052 but does not directly expose BED, H5 or H6,
   so it is not assumed to be a universal optimum.
2. `Q0100_W0100_az270_el15_H1H7_v5_Qnorm_adapt_HRRmax`: measured peak
   HRRPUA upper-bound sensitivity at the baseline angle. BED Nylon=790,
   curtain=324, seat PU=860, H6 PVC=259 and H7 chloroprene=458 kW/m2.
3. `Q0100_W0100_az270_el15_H1H7_v5_Qnorm_adapt_BA`: BURN_AWAY sensitivity
   on NLZW, JAZPM, PVCSL and CRXJ only. Aluminium surfaces remain non-burning.

The HRRPUA values are deliberately marked as upper-bound sensitivities rather
than calibrated material replacements. Sources are the NIST/transportation
cone-calorimeter tables for privacy-curtain and chloroprene components, the
NIST polyurethane data and aircraft-cabin PU cone study, and published cone
tests for neat Nylon-6 and PVC. Cone peak HRR depends on formulation, specimen
orientation and imposed flux, so specimen-specific values remain preferable.

`BURN_AWAY` is not expected to increase heat release by itself. It tests the
competing effects of opening radiative/flow paths and removing sustained fuel.
Its result must not be interpreted as a material calibration.
# 2026-07-22 surface-layer thickness audit

The active corrected baselines and threshold campaign were preserved unchanged. A new,
separately named Q100 sensitivity case was generated to correct values that had treated
component depth as FDS one-dimensional `SURF` material-layer thickness:

| Group | Previous | Audited value | Basis |
|---|---:|---:|---|
| RADM E-glass | 120 mm | 100 mm | restored latest PyroSim export; still pending specimen verification |
| WINS acrylic | 75 mm | 25 mm | restored latest PyroSim export |
| BED nylon cover | 120 mm | 0.89 mm | conservative representative nylon upholstery-fabric upper value; provisional |
| CURT nylon fabric | 30 mm | 3 mm | restored latest PyroSim export and matches material name |
| U4 epoxy GFRP | 30 mm | 6 mm | restored latest PyroSim export |

The seat foam core (150 mm), metal skins and H1-H7 equipment thicknesses were retained.
The `OBST` geometry, Q=100 J/cm2 incident-plane normalization, W=100 kt, azimuth 270,
elevation 15, HRRPUA, ignition temperatures, probes and damage criteria are unchanged.
All base and radiation-bin-derived `SURF` records are updated together by
`src/build_q100_thickness_corrected_variant.py`.

The node03 queue was replaced while it was idle and waiting (no FDS process was
terminated). It now contains only the Q100 thickness-audit case. The older BED-HRR,
angle, HRRmax and BURN_AWAY variants remain preserved on disk but are not allowed to
start with the superseded thicknesses. Any still-needed follow-up will be regenerated
from the thickness-audit baseline and will change one additional factor at a time.

At the user's request, the superseded active Q100 on node01 and Q200 on node05 were
stopped on 2026-07-22. The node05 continuation queue and node03 waiting queue were also
stopped so they cannot launch old-thickness inputs. The active node04 Q400 threshold
case and its threshold controller were explicitly preserved. A new 32-process campaign
was generated for Q=100, 200, 300 and 400 J/cm2 at W=100 kt, az=270 and el=15 using the
same audited thicknesses. Q100 uses the physically equivalent validated 20-way mesh
assignment because node01 has 20 logical CPUs; Q200-Q400 use 32-way assignments. The
queue idle check was corrected to use each case's actual MPI requirement rather than a
hard-coded 32-core reservation. A 20% low-load floor permits a full-node case after
active FDS process count has reached zero while still rejecting a materially busy node.
These cases are built by
`src/build_thickness_corrected_campaign.py`; all non-Q inputs are identical.

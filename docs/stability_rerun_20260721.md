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

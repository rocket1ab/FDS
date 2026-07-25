# Q400 Favorable-Angle Combined Case

## Case

`Q0400_W0100_az060_el75_H1H7_v6_combined_RF040_BA0_shell4`

This is a separately classified engineering scenario. It preserves Q=400
J/cm2, W=100 kt, T_END=1500 s, the filled U06 seat geometry, the 4 mm
RADM/AL2024/AL7075 equivalent response layers, ignition inputs, probes and
damage criteria.

## Rationale

The DDA direction is az=60 deg and el=75 deg because the completed lower-HRR
filled-seat case at this angle reached 10/17 severe groups, compared with 5/17
at az=270 deg and el=15 deg.

The bounded combustion inputs are:

| Group | HRRPUA (kW/m2) |
|---|---:|
| SEAT | 650 |
| BED | 600 |
| CURT | 400 |

`RADIATIVE_FRACTION=0.40` and `BURN_AWAY=.FALSE.` are retained. These HRRPUA
values are applied consistently to both base and DDA-derived SURF definitions.
This fixes the prior case-generation inconsistency where a secondarily ignited
base surface could retain a lower HRRPUA than its irradiated counterpart.

Q, material thermal properties and damage thresholds are not changed. The
existing az60 voxel build has 257 occupied seat cells versus 256 in the az270
comparison, a known 0.001 m3 geometry delta that must be reported.

## Submission

Static validation passed with incident-plane normalization and a maximum local
integrated fluence of 388.51 J/cm2. The case was submitted to the independent
node04 capacity slot `q400_angle_combined_node04`. It waits until the existing
factory workload leaves sufficient load headroom, then performs the standard
short preflight before starting one 32-MPI FDS run.

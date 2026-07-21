# Q100 physically normalized adjustment experiment

## Motivation

The baseline Q100 case labels the incident-plane fluence as 100 J/cm2, but its
maximum applied local surface flux is 437 kW/m2. With the current nuclear ramp
integral of 0.660398 s, that is only 28.86 J/cm2 at the hottest local face.
This energy mismatch is addressed before changing material properties or
damage thresholds.

## Angle scan

Forty directions were evaluated by rerunning the voxel visibility calculation
at eight azimuths and five elevations. A single direction illuminated at most
13 of 17 monitored groups. U4 and H6 remained shielded in every tested
direction. Changing angle alone therefore cannot guarantee all-device damage.
The full result is stored in `reports/incident_angle_scan.csv`.

The new comparison retains 270 deg azimuth and 15 deg elevation. This direction
directly covers the mattress, H1, H2 and H5 and isolates energy normalization
from geometry changes. A later angle comparison should be a separate case.

## New case

Case: `Q0100_W0100_az270_el15_H1H7_v5_Qnorm`

The incident-plane peak irradiance is calculated from

`E0 = (Q * 10 kJ/m2 per J/cm2) / integral(F dt)`.

For Q=100 J/cm2 and integral(F dt)=0.660398 s, E0 is 1514.238 kW/m2. After
projection and voxel shielding, the maximum local flux is 1471 kW/m2 and the
maximum local integrated fluence is 97.145 J/cm2.

All geometry, material properties, ignition temperatures, HRRPUA values,
reaction parameters, damage thresholds, pulse shape and `BURN_AWAY=FALSE`
remain unchanged. The case runs to 1500 s using a validated 20-process mesh
partition on node01. A 0.01 s FDS preflight completed successfully before the
formal run was launched.

## Campaign decision

The legacy scaling is retired because its case label did not represent the
specified incident-plane fluence. The Q-normalized formulation is now the only
valid baseline for Q50, Q100, Q200, Q300 and Q400 comparisons. Existing legacy
outputs are retained only as provenance and must not be used to infer a fluence
threshold.

Node01 continues the corrected Q100 comparison. Node04 runs corrected Q300,
and node05 runs corrected Q50, Q200 and Q400 sequentially. Each production
case runs to 1500 s and is accepted only after normal FDS completion and damage
assessment.

If corrected Q100 still cannot damage H1-H7, the next physically defensible
step is to model internal electronic components and use documented electronics
thermal failure criteria. Arbitrarily reducing the 3 mm aluminium shell
thickness or raising HRRPUA is not accepted as evidence of a Q100 threshold.

# Lessons learned from the aircraft damage campaigns

Updated: 2026-07-22

This document separates conclusions supported by completed or inspected cases from
working hypotheses that still require controlled FDS comparisons. Legacy outputs are
retained for provenance, but only the corrected incident-plane-normalized cases may be
used to infer a fluence threshold.

## 1. Heat-flux normalization must be verified before damage interpretation

The retired scaling rule derived every case from a Q400 peak flux. Its nominal Q100
case delivered only 28.86 J/cm2 at the hottest local face because the applied peak was
437 kW/m2 and the pulse integral was 0.660398 s. The corrected rule is

`E0 = 10 Q / integral(F dt)`,

where Q is in J/cm2 and E0 is in kW/m2. The corrected Q100 case gives a maximum local
integrated fluence of 97.145 J/cm2 after projection and DDA shielding. Corresponding
local maxima for nominal Q50-Q400 are 48.539, 97.145, 194.223, 291.368 and
388.512 J/cm2. A case label is therefore insufficient evidence; every campaign must
report the time-integrated local flux actually applied to the exposed faces.

An old case with a constant `EXTERNAL_FLUX` and no nuclear ramp can heat a surface for
the full simulation instead of only during the nuclear pulse. Its high temperatures or
damage count are useful for diagnosing model sensitivity, but not for determining a
nuclear-flash fluence threshold.

## 2. Numerical stability depends strongly on the flux-boundary representation

The unstable updated model used 1912 generated overlay VENT records, whereas a stable
completed reference attached the external flux directly to split OBST faces through
`SURF_ID6`. Removing the overlay VENT representation and returning to non-overlapping
split OBST faces was the most important stability correction. A successful short
preflight only proves that FDS accepts the input; acceptance requires passing the prior
176.87-179.09 s instability window and ultimately reaching a normal stop at 1500 s.

## 3. Geometry and shielding prevent one angle from directly heating every group

The 40-direction DDA scan found that one direction directly illuminated at most 13 of
17 monitored groups. U4 and H6 remained shielded in every sampled direction. At the
current azimuth/elevation of 270/15 deg, several devices are heated mainly by secondary
cabinfire exposure rather than direct flash. Increasing Q cannot remove geometric
shadowing; angle sensitivity, nearby combustible sources and secondary heat transfer
must be evaluated separately.

The practical sequence is to run a DDA visibility scan first, then select angles that
improve exposure of the currently undamaged groups. No angle should be called optimal
solely because it maximizes the global illuminated-face count.

## 4. SURF thickness must represent the physical material layer

Several earlier SURF values represented component depth rather than the thickness of
the one-dimensional surface material. The most consequential example was BED, where
120 mm had been assigned to nylon even though the nylon is a thin mattress cover. The
audited provisional value is 0.89 mm. CURT was corrected to 3 mm, WINS to 25 mm and U4
to 6 mm; RADM remains 100 mm pending measurement.

An excessive layer thickness increases thermal inertia and can suppress ignition or
delay the surface-temperature response. Thickness must be traced to the actual skin,
cover, glazing or panel represented by MATL, not copied automatically from the OBST
bounding-box dimension. Material-specific measurements remain preferable to the
provisional values.

## 5. Peak temperature alone is not a damage result

The inspected corrected Q400 BED data reached approximately 691 C at a monitored
location but did not satisfy the required continuous time above 500 C. Damage must be
evaluated using the specified temperature-duration criterion, not the maximum sample
alone. The same distinction applies to ignition: briefly crossing the ignition
temperature does not demonstrate sustained combustion.

For each group the report should include the maximum among valid redundant probes,
continuous time above each threshold, HRR/HRRPUA after the flash pulse and the reason
for any failed criterion. The probe maximum is a monitored spatial maximum, not the
mathematical maximum over every surface cell; BNDF wall-temperature and net-heat-flux
fields provide the full-surface cross-check.

## 6. Probe redundancy is necessary but invalid probes must be excluded

The initial v5 geometry audit found six WT/HF probe pairs more than one grid cell from
their intended faces. The v6 correction validates all 153 temperature/heat-flux pairs
at a 0.035 m face offset. Multiple probes per material are needed because the hottest
location can move and a local surface can burn away. Assessment should use the maximum
of currently valid probes and retain the achieved damage level once a severe criterion
has already been satisfied.

Shielded groups with no directly irradiated probe are not probe failures. Their probes
measure secondary heating and must be interpreted together with DDA visibility.

## 7. HRRPUA changes combustion after ignition, not the absorbed flash energy

Raising HRRPUA can increase flame heat feedback and improve sustained burning only
after a combustible surface has ignited. It cannot directly heat H1-H5 aluminium
equipment, remove shielding or compensate for an incorrect external-flux integral.
The current upper-HRRPUA campaign is therefore a bounding sensitivity, not calibrated
proof that the actual aircraft materials release those rates.

The source-backed upper values are RADM 840, WINS 806, BED 790, CURT 324, U4 840,
SEAT 860, H6 259 and H7 458 kW/m2. H1-H5 remain non-combustible. Conclusions must be
compared against the same-Q audited-thickness baseline and replaced when specimen cone
calorimeter data become available.

## 8. BURN_AWAY is not a general method for increasing damage

`BURN_AWAY=TRUE` removes consumed solid cells. It may expose shielded objects or alter
ventilation, but it can also remove the fuel and reduce sustained heat release. It does
not increase HRRPUA by itself. BURN_AWAY should be tested only for physically removable
combustible layers and as a separate one-factor sensitivity; aluminium surfaces must
not be treated as burn-away fuel.

## 9. Yield at fixed fluence is a pulse-shape sensitivity

At fixed Q, increasing yield lengthens the pulse while reducing its peak irradiance;
it does not increase total incident energy. A longer pulse may help thick or conductive
components accumulate heat and remain above a duration threshold, but its lower peak
can make ignition of combustible surfaces harder. Yield should therefore be varied only
after Q normalization, using the same geometry and angle, and interpreted as a
pulse-duration/peak-flux trade-off.

A useful Q100 comparison is W=50, 100, 300 and 1000 kt. The current expectation that
200-300 kt may balance ignition and sustained heating is a hypothesis, not an established
result.

## 10. Recommended threshold-search discipline

1. Verify FDS input, DDA visibility, local integrated fluence, probe geometry and a
   0.01 s preflight before production.
2. Preserve a corrected baseline and change one physical factor per adaptive variant.
3. Accept a case only after `STOP: FDS completed successfully` at 1500 s and completed
   damage assessment; early temperatures are provisional.
4. Establish a failed lower bound and an all-severe upper bound before bisection.
5. Keep geometry, materials, yield, angle, probes and damage criteria fixed during a
   fluence-only threshold search.
6. Do not combine legacy-flux, old-thickness, HRRPUA-upper or BURN_AWAY variants in one
   threshold bracket.

## Current interpretation

The available evidence does not yet show that Q100 can cause severe damage to all 17
groups under the baseline 270/15 deg geometry. The main limiting mechanisms are local
shielding, insufficient temperature duration, uncertain combustible-layer properties
and the need for secondary cabin-fire heating. The active Q50-Q400 upper-HRRPUA campaign
will determine whether stronger post-ignition burning materially changes those limits;
it must not be treated as successful until each case completes and is assessed.

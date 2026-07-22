# Source-backed upper HRRPUA campaign, 2026-07-22

This is an upper-bound sensitivity campaign, not a replacement for qualification
data measured from the actual aircraft materials. The preceding audited-thickness
campaign was stopped without deleting its inputs or outputs.

| Group | Baseline | Upper sensitivity | Basis |
|---|---:|---:|---|
| RADM epoxy/glass | 75 | 840 | Uncoated GRE cone peak at 50 kW/m2 |
| WINS PMMA | 250 | 806 | FSRI PMMA maximum reported replicate peak |
| BED nylon cover | 180 | 790 | Neat Nylon-6 bounding peak; provisional for the cover |
| CURT nylon fabric | 180 | 324 | NIST transportation privacy-curtain maximum peak |
| U4 epoxy/glass | 100 | 840 | Uncoated GRE cone peak at 50 kW/m2 |
| SEAT PU foam | 200 | 860 | Raw aircraft-cabin PU peak of 859.9 kW/m2 |
| H6 PVC | 200 | 259 | PVC cone maximum at 50 kW/m2 |
| H7 chloroprene | 180 | 458 | NIST chloroprene diaphragm maximum peak |

Units are kW/m2. H1-H5 and the aluminium/oxygen-tank groups remain non-combustible.
Q normalization, W=100 kt, az=270 deg, el=15 deg, T_END=1500 s, geometry,
ignition temperatures, BURN_AWAY, probes, and damage criteria are unchanged.

Run allocation prioritizes an early upper-bound check while retaining all requested
fluences: node01 Q50; node04 Q400 then Q300; node05 Q200 then Q100. Each node runs
one FDS case at a time.

Preflight corrections made before launch:

* Q50 maps the 32 MESH records contiguously and monotonically onto MPI ranks 0-19.
* The preflight parser now edits `T_END` only inside the `&TIME` record, avoiding
  matches in descriptive comments. All five inputs retain `T_END=1500 s`.

Campaign-wide conclusions and reusable modeling guidance are maintained in
[`modeling_lessons_20260722.md`](modeling_lessons_20260722.md).

# Complete damage-tree assessment: Q0050_W0100_az270_el15_H1H7_v4_legacy_stable

- Simulation time: **919.50 s**
- Source directory: `cases_legacy_stable/Q0050_W0100_az270_el15_H1H7_v4_legacy_stable`
- Campaign classification: **retired legacy-flux provenance**
- PDF aircraft-tree level: **SEVERE**
- Strict all-equipment severe result: **2/17** (`all_severe=false`)
- Maximum temperature: dynamic envelope of geometrically valid redundant wall-temperature probes.
- Important: the strict 17/17 metric is not the PDF aircraft-level rule.

## Damage tree

![Damage tree](damage_tree.svg)

## System propagation

| System | Level | Trigger nodes | Applied rule |
|---|---:|---|---|
| Airframe structure (`airframe`) | moderate | AL7075 | a major item is moderate or a secondary item is severe |
| Avionics system (`avionics`) | none | none | all mapped items are known and none is damaged |
| Power system (`power`) | mild | H5 | at least one known item is mild and no higher rule is met |
| Cockpit system (`cockpit`) | severe | SEAT, H3 | at least one major item is severe |

## Complete equipment assessment

| Group | Equipment | Role | Level | Peak C | Mild evidence | Moderate evidence | Severe evidence | Valid probes |
|---|---|---|---:|---:|---|---|---|---:|
| RADM | Nose/radome | airframe:major | none | 107.7 | 150 C; 0.0/300 s | 250 C; 0.0/180 s | 400 C; 0.0/180 s | 10 |
| WINS | PMMA windows | cockpit:major | none | 150.7 | 120 C; 0.0/60 s | 200 C; 0.0/45 s | 250 C; 0.0/8 s | 10 |
| BED | Nylon mattress | cockpit:major | none | 169.7 | 200 C; 0.0/60 s | 250 C; 0.0/90 s | 500 C; 0.0/5 s | 8 |
| CURT | Nylon curtain | cockpit:major | none | 119.6 | 200 C; 0.0/60 s | 250 C; 0.0/90 s | 500 C; 0.0/5 s | 10 |
| U4 | U4 instrument equipment | cockpit:major | mild | 212.5 | 120 C; 667.5/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 6 |
| SEAT | Polyurethane seats | cockpit:major | severe | 2163.6 | 200 C; 918.0/60 s | 300 C; 918.0/90 s | 500 C; 918.0/5 s | 10 |
| AL2024 | Aluminium 2024 skin | airframe:major | mild | 260.8 | 120 C; 831.0/600 s | 250 C; 33.0/300 s | 400 C; 0.0/60 s | 10 |
| AL5052 | Aluminium 5052 duct | cockpit:secondary | moderate | 272.2 | 120 C; 546.0/600 s | 250 C; 316.5/300 s | 400 C; 0.0/60 s | 10 |
| AL7075 | Aluminium 7075 frame | airframe:major | moderate | 241.1 | 120 C; 666.0/600 s | 200 C; 322.5/240 s | 400 C; 0.0/60 s | 10 |
| O2TANK | Oxygen tank | cockpit:secondary | none | 186.7 | 120 C; 487.5/600 s | 200 C; 0.0/240 s | 400 C; 0.0/60 s | 10 |
| H1 | Navigation subsystem | avionics:major | none | 62.7 | 120 C; 0.0/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 7 |
| H2 | Mission subsystem | avionics:major | none | 37.7 | 120 C; 0.0/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 10 |
| H3 | Display subsystem | cockpit:major | severe | 471.3 | 120 C; 661.5/300 s | 250 C; 478.5/180 s | 400 C; 348.0/5 s | 14 |
| H4 | Communication subsystem | avionics:secondary | none | 133.3 | 120 C; 217.5/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 10 |
| H5 | Battery | power:major | mild | 153.6 | 100 C; 403.5/60 s | 150 C; 34.5/600 s | 200 C; 0.0/180 s | 6 |
| H6 | Power transmission subsystem | power:major | none | 305.5 | 120 C; 679.5/1200 s | 200 C; 537.0/600 s | 400 C; 0.0/180 s | 8 |
| H7 | Flight-control subsystem | cockpit:major | mild | 185.3 | 120 C; 754.5/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 4 |

## Assessment interpretation

- Non-severe or unknown groups: **RADM, WINS, BED, CURT, U4, AL2024, AL5052, AL7075, O2TANK, H1, H2, H4, H5, H6, H7**.
- Aircraft level is propagated from the highest system level: **severe**.
- H2 (mission) and H3 (display) are model-specific mappings; their generic electronics thresholds are not same-name PDF rows.
- H1-H4 probes currently measure aluminium enclosure surface temperature as a proxy for internal electronics temperature.


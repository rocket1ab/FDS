# Complete damage-tree assessment: Q0300_W0100_az270_el15_H1H7_v5_Qnorm

- Simulation time: **1500.00 s**
- Source directory: `cases_qnorm/Q0300_W0100_az270_el15_H1H7_v5_Qnorm`
- Campaign classification: **corrected Q-normalized baseline**
- PDF aircraft-tree level: **SEVERE**
- Strict all-equipment severe result: **4/17** (`all_severe=false`)
- Maximum temperature: dynamic envelope of geometrically valid redundant wall-temperature probes.
- Important: the strict 17/17 metric is not the PDF aircraft-level rule.

## Damage tree

![Damage tree](damage_tree.svg)

## System propagation

| System | Level | Trigger nodes | Applied rule |
|---|---:|---|---|
| Airframe structure (`airframe`) | severe | AL2024 | at least one major item is severe |
| Avionics system (`avionics`) | mild | H2, H4 | at least one known item is mild and no higher rule is met |
| Power system (`power`) | none | none | all mapped items are known and none is damaged |
| Cockpit system (`cockpit`) | severe | WINS, SEAT, H3 | at least one major item is severe |

## Complete equipment assessment

| Group | Equipment | Role | Level | Peak C | Mild evidence | Moderate evidence | Severe evidence | Valid probes |
|---|---|---|---:|---:|---|---|---|---:|
| RADM | Nose/radome | airframe:major | moderate | 1300.8 | 150 C; 1498.5/300 s | 250 C; 894.0/180 s | 400 C; 7.5/180 s | 10 |
| WINS | PMMA windows | cockpit:major | severe | 1504.1 | 120 C; 1498.5/60 s | 200 C; 1498.5/45 s | 250 C; 1498.5/8 s | 10 |
| BED | Nylon mattress | cockpit:major | none | 547.6 | 200 C; 45.0/60 s | 250 C; 19.5/90 s | 500 C; 0.0/5 s | 8 |
| CURT | Nylon curtain | cockpit:major | moderate | 1330.1 | 200 C; 1237.5/60 s | 250 C; 1011.0/90 s | 500 C; 4.5/5 s | 10 |
| U4 | U4 instrument equipment | cockpit:major | moderate | 267.4 | 120 C; 1140.0/300 s | 250 C; 330.0/180 s | 400 C; 0.0/5 s | 6 |
| SEAT | Polyurethane seats | cockpit:major | severe | 2726.8 | 200 C; 1498.5/60 s | 300 C; 1498.5/90 s | 500 C; 1498.5/5 s | 10 |
| AL2024 | Aluminium 2024 skin | airframe:major | severe | 550.9 | 120 C; 1498.5/600 s | 250 C; 1498.5/300 s | 400 C; 1497.0/60 s | 10 |
| AL5052 | Aluminium 5052 duct | cockpit:secondary | moderate | 371.1 | 120 C; 1324.5/600 s | 250 C; 1185.0/300 s | 400 C; 0.0/60 s | 10 |
| AL7075 | Aluminium 7075 frame | airframe:major | mild | 330.0 | 120 C; 1498.5/600 s | 200 C; 160.5/240 s | 400 C; 0.0/60 s | 10 |
| O2TANK | Oxygen tank | cockpit:secondary | moderate | 235.9 | 120 C; 1497.0/600 s | 200 C; 489.0/240 s | 400 C; 0.0/60 s | 8 |
| H1 | Navigation subsystem | avionics:major | none | 363.5 | 120 C; 295.5/300 s | 250 C; 79.5/180 s | 400 C; 0.0/5 s | 6 |
| H2 | Mission subsystem | avionics:major | mild | 368.1 | 120 C; 408.0/300 s | 250 C; 121.5/180 s | 400 C; 0.0/5 s | 8 |
| H3 | Display subsystem | cockpit:major | severe | 589.6 | 120 C; 1327.5/300 s | 250 C; 1267.5/180 s | 400 C; 1195.5/5 s | 14 |
| H4 | Communication subsystem | avionics:secondary | mild | 197.8 | 120 C; 1471.5/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 10 |
| H5 | Battery | power:major | none | 90.4 | 100 C; 0.0/60 s | 150 C; 0.0/600 s | 200 C; 0.0/180 s | 6 |
| H6 | Power transmission subsystem | power:major | none | 258.8 | 120 C; 936.0/1200 s | 200 C; 46.5/600 s | 400 C; 0.0/180 s | 8 |
| H7 | Flight-control subsystem | cockpit:major | mild | 335.8 | 120 C; 1486.5/300 s | 250 C; 43.5/180 s | 400 C; 0.0/5 s | 3 |

## Assessment interpretation

- Non-severe or unknown groups: **RADM, BED, CURT, U4, AL5052, AL7075, O2TANK, H1, H2, H4, H5, H6, H7**.
- Aircraft level is propagated from the highest system level: **severe**.
- H2 (mission) and H3 (display) are model-specific mappings; their generic electronics thresholds are not same-name PDF rows.
- H1-H4 probes currently measure aluminium enclosure surface temperature as a proxy for internal electronics temperature.


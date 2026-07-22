# Complete damage-tree assessment: Q0100_W0100_az270_el15_H1H7_v5_Qnorm

- Simulation time: **709.50 s**
- Source directory: `cases_exploratory/Q0100_W0100_az270_el15_H1H7_v5_Qnorm`
- Campaign classification: **cases_exploratory**
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
| Avionics system (`avionics`) | none | none | all mapped items are known and none is damaged |
| Power system (`power`) | none | none | all mapped items are known and none is damaged |
| Cockpit system (`cockpit`) | severe | WINS, SEAT, H3 | at least one major item is severe |

## Complete equipment assessment

| Group | Equipment | Role | Level | Peak C | Mild evidence | Moderate evidence | Severe evidence | Valid probes |
|---|---|---|---:|---:|---|---|---|---:|
| RADM | Nose/radome | airframe:major | none | 574.0 | 150 C; 13.5/300 s | 250 C; 4.5/180 s | 400 C; 1.5/180 s | 10 |
| WINS | PMMA windows | cockpit:major | severe | 895.4 | 120 C; 708.0/60 s | 200 C; 708.0/45 s | 250 C; 708.0/8 s | 10 |
| BED | Nylon mattress | cockpit:major | none | 208.3 | 200 C; 0.0/60 s | 250 C; 0.0/90 s | 500 C; 0.0/5 s | 8 |
| CURT | Nylon curtain | cockpit:major | moderate | 628.8 | 200 C; 361.5/60 s | 250 C; 193.5/90 s | 500 C; 0.0/5 s | 10 |
| U4 | U4 instrument equipment | cockpit:major | mild | 190.4 | 120 C; 304.5/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 6 |
| SEAT | Polyurethane seats | cockpit:major | severe | 2166.5 | 200 C; 708.0/60 s | 300 C; 708.0/90 s | 500 C; 708.0/5 s | 10 |
| AL2024 | Aluminium 2024 skin | airframe:major | severe | 473.1 | 120 C; 706.5/600 s | 250 C; 697.5/300 s | 400 C; 639.0/60 s | 10 |
| AL5052 | Aluminium 5052 duct | cockpit:secondary | moderate | 329.3 | 120 C; 510.0/600 s | 250 C; 333.0/300 s | 400 C; 0.0/60 s | 10 |
| AL7075 | Aluminium 7075 frame | airframe:major | none | 154.4 | 120 C; 433.5/600 s | 200 C; 0.0/240 s | 400 C; 0.0/60 s | 10 |
| O2TANK | Oxygen tank | cockpit:secondary | none | 148.3 | 120 C; 256.5/600 s | 200 C; 0.0/240 s | 400 C; 0.0/60 s | 8 |
| H1 | Navigation subsystem | avionics:major | none | 136.9 | 120 C; 43.5/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 6 |
| H2 | Mission subsystem | avionics:major | none | 137.0 | 120 C; 46.5/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 8 |
| H3 | Display subsystem | cockpit:major | severe | 534.8 | 120 C; 511.5/300 s | 250 C; 444.0/180 s | 400 C; 361.5/5 s | 14 |
| H4 | Communication subsystem | avionics:secondary | none | 132.6 | 120 C; 130.5/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 10 |
| H5 | Battery | power:major | none | 74.4 | 100 C; 0.0/60 s | 150 C; 0.0/600 s | 200 C; 0.0/180 s | 6 |
| H6 | Power transmission subsystem | power:major | none | 231.9 | 120 C; 621.0/1200 s | 200 C; 36.0/600 s | 400 C; 0.0/180 s | 8 |
| H7 | Flight-control subsystem | cockpit:major | mild | 270.5 | 120 C; 691.5/300 s | 250 C; 10.5/180 s | 400 C; 0.0/5 s | 3 |

## Assessment interpretation

- Non-severe or unknown groups: **RADM, BED, CURT, U4, AL5052, AL7075, O2TANK, H1, H2, H4, H5, H6, H7**.
- Aircraft level is propagated from the highest system level: **severe**.
- H2 (mission) and H3 (display) are model-specific mappings; their generic electronics thresholds are not same-name PDF rows.
- H1-H4 probes currently measure aluminium enclosure surface temperature as a proxy for internal electronics temperature.


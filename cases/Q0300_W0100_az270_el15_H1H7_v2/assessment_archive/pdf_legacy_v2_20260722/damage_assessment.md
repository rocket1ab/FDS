# Complete damage-tree assessment: Q0300_W0100_az270_el15_H1H7_v2

- Simulation time: **177.00 s**
- Source directory: `cases/Q0300_W0100_az270_el15_H1H7_v2`
- Campaign classification: **developmental provenance**
- PDF aircraft-tree level: **SEVERE**
- Strict all-equipment severe result: **3/17** (`all_severe=false`)
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
| Cockpit system (`cockpit`) | severe | WINS, SEAT | at least one major item is severe |

## Complete equipment assessment

| Group | Equipment | Role | Level | Peak C | Mild evidence | Moderate evidence | Severe evidence | Valid probes |
|---|---|---|---:|---:|---|---|---|---:|
| RADM | Nose/radome | airframe:major | none | 520.0 | 150 C; 10.5/300 s | 250 C; 3.0/180 s | 400 C; 0.0/180 s | 10 |
| WINS | PMMA windows | cockpit:major | severe | 856.7 | 120 C; 175.5/60 s | 200 C; 175.5/45 s | 250 C; 175.5/8 s | 10 |
| BED | Nylon mattress | cockpit:major | none | 188.5 | 200 C; 0.0/60 s | 250 C; 0.0/90 s | 500 C; 0.0/5 s | 8 |
| CURT | Nylon curtain | cockpit:major | none | 573.1 | 200 C; 22.5/60 s | 250 C; 4.5/90 s | 500 C; 0.0/5 s | 10 |
| U4 | U4 instrument equipment | cockpit:major | none | 79.3 | 120 C; 0.0/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 6 |
| SEAT | Polyurethane seats | cockpit:major | severe | 1415.2 | 200 C; 175.5/60 s | 300 C; 175.5/90 s | 500 C; 175.5/5 s | 10 |
| AL2024 | Aluminium 2024 skin | airframe:major | severe | 444.7 | 120 C; 174.0/600 s | 250 C; 156.0/300 s | 400 C; 88.5/60 s | 10 |
| AL5052 | Aluminium 5052 duct | cockpit:secondary | none | 67.4 | 120 C; 0.0/600 s | 250 C; 0.0/300 s | 400 C; 0.0/60 s | 10 |
| AL7075 | Aluminium 7075 frame | airframe:major | none | 113.9 | 120 C; 0.0/600 s | 200 C; 0.0/240 s | 400 C; 0.0/60 s | 10 |
| O2TANK | Oxygen tank | cockpit:secondary | none | 86.3 | 120 C; 0.0/600 s | 200 C; 0.0/240 s | 400 C; 0.0/60 s | 10 |
| H1 | Navigation subsystem | avionics:major | none | 124.4 | 120 C; 12.0/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 7 |
| H2 | Mission subsystem | avionics:major | none | 124.6 | 120 C; 13.5/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 10 |
| H3 | Display subsystem | cockpit:major | none | 90.9 | 120 C; 0.0/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 14 |
| H4 | Communication subsystem | avionics:secondary | none | 92.5 | 120 C; 0.0/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 10 |
| H5 | Battery | power:major | none | 57.7 | 100 C; 0.0/60 s | 150 C; 0.0/600 s | 200 C; 0.0/180 s | 6 |
| H6 | Power transmission subsystem | power:major | none | 192.9 | 120 C; 27.0/1200 s | 200 C; 0.0/600 s | 400 C; 0.0/180 s | 8 |
| H7 | Flight-control subsystem | cockpit:major | none | 225.6 | 120 C; 154.5/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 4 |

## Assessment interpretation

- Non-severe or unknown groups: **RADM, BED, CURT, U4, AL5052, AL7075, O2TANK, H1, H2, H3, H4, H5, H6, H7**.
- Aircraft level is propagated from the highest system level: **severe**.
- H2 (mission) and H3 (display) are model-specific mappings; their generic electronics thresholds are not same-name PDF rows.
- H1-H4 probes currently measure aluminium enclosure surface temperature as a proxy for internal electronics temperature.


# Complete damage-tree assessment: Q0100_W0100_az270_el15_H1H7_v5_Qnorm_adapt_thickness_audit

- Simulation time: **54.00 s**
- Source directory: `cases_adaptive/Q0100_W0100_az270_el15_H1H7_v5_Qnorm_adapt_thickness_audit`
- Campaign classification: **adaptive sensitivity; compare separately**
- PDF aircraft-tree level: **SEVERE**
- Strict all-equipment severe result: **2/17** (`all_severe=false`)
- Maximum temperature: dynamic envelope of geometrically valid redundant wall-temperature probes.
- Important: the strict 17/17 metric is not the PDF aircraft-level rule.

## Damage tree

![Damage tree](damage_tree.svg)

## System propagation

| System | Level | Trigger nodes | Applied rule |
|---|---:|---|---|
| Airframe structure (`airframe`) | none | none | all mapped items are known and none is damaged |
| Avionics system (`avionics`) | none | none | all mapped items are known and none is damaged |
| Power system (`power`) | none | none | all mapped items are known and none is damaged |
| Cockpit system (`cockpit`) | severe | WINS, SEAT | at least one major item is severe |

## Complete equipment assessment

| Group | Equipment | Role | Level | Peak C | Mild evidence | Moderate evidence | Severe evidence | Valid probes |
|---|---|---|---:|---:|---|---|---|---:|
| RADM | Nose/radome | airframe:major | none | 567.5 | 150 C; 13.5/300 s | 250 C; 4.5/180 s | 400 C; 1.5/180 s | 10 |
| WINS | PMMA windows | cockpit:major | severe | 784.5 | 120 C; 52.5/60 s | 200 C; 52.5/45 s | 250 C; 52.5/8 s | 10 |
| BED | Nylon mattress | cockpit:major | none | 264.3 | 200 C; 27.0/60 s | 250 C; 9.0/90 s | 500 C; 0.0/5 s | 8 |
| CURT | Nylon curtain | cockpit:major | none | 626.5 | 200 C; 52.5/60 s | 250 C; 24.0/90 s | 500 C; 0.0/5 s | 10 |
| U4 | U4 instrument equipment | cockpit:major | none | 82.5 | 120 C; 0.0/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 6 |
| SEAT | Polyurethane seats | cockpit:major | severe | 1363.9 | 200 C; 52.5/60 s | 300 C; 52.5/90 s | 500 C; 52.5/5 s | 10 |
| AL2024 | Aluminium 2024 skin | airframe:major | none | 352.7 | 120 C; 51.0/600 s | 250 C; 43.5/300 s | 400 C; 0.0/60 s | 10 |
| AL5052 | Aluminium 5052 duct | cockpit:secondary | none | 39.7 | 120 C; 0.0/600 s | 250 C; 0.0/300 s | 400 C; 0.0/60 s | 10 |
| AL7075 | Aluminium 7075 frame | airframe:major | none | 125.1 | 120 C; 18.0/600 s | 200 C; 0.0/240 s | 400 C; 0.0/60 s | 10 |
| O2TANK | Oxygen tank | cockpit:secondary | none | 82.7 | 120 C; 0.0/600 s | 200 C; 0.0/240 s | 400 C; 0.0/60 s | 8 |
| H1 | Navigation subsystem | avionics:major | none | 136.9 | 120 C; 43.5/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 6 |
| H2 | Mission subsystem | avionics:major | none | 137.0 | 120 C; 46.5/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 8 |
| H3 | Display subsystem | cockpit:major | none | 62.1 | 120 C; 0.0/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 14 |
| H4 | Communication subsystem | avionics:secondary | none | 105.0 | 120 C; 0.0/300 s | 250 C; 0.0/180 s | 400 C; 0.0/5 s | 10 |
| H5 | Battery | power:major | none | 20.6 | 100 C; 0.0/60 s | 150 C; 0.0/600 s | 200 C; 0.0/180 s | 6 |
| H6 | Power transmission subsystem | power:major | none | 32.8 | 120 C; 0.0/1200 s | 200 C; 0.0/600 s | 400 C; 0.0/180 s | 8 |
| H7 | Flight-control subsystem | cockpit:major | none | 313.7 | 120 C; 36.0/300 s | 250 C; 22.5/180 s | 400 C; 0.0/5 s | 3 |

## Assessment interpretation

- Non-severe or unknown groups: **RADM, BED, CURT, U4, AL2024, AL5052, AL7075, O2TANK, H1, H2, H3, H4, H5, H6, H7**.
- Aircraft level is propagated from the highest system level: **severe**.
- H2 (mission) and H3 (display) are model-specific mappings; their generic electronics thresholds are not same-name PDF rows.
- H1-H4 probes currently measure aluminium enclosure surface temperature as a proxy for internal electronics temperature.


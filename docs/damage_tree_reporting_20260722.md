# Complete damage-tree reporting

Implemented: 2026-07-22

Every successful FDS case is now followed by a complete assessment based on
`aircraft_damage_standard_20260711.pdf`, Tables 9-15 and Section 6.3. The assessment
keeps the PDF aircraft-tree result separate from the stricter research objective that
requires every monitored group to be severe.

## Automatic outputs per completed case

The queue calls `src/assess_results.py` only after the FDS log contains
`STOP: FDS completed successfully` and no numerical instability. The case directory
then receives:

* `damage_assessment.json`: machine-readable probe evidence, equipment levels, system
  propagation evidence, aircraft level and strict severe count.
* `damage_assessment.md`: complete equipment table, temperature-duration evidence,
  system triggers, aircraft result and interpretation.
* `damage_tree.svg`: color-coded aircraft-system-equipment tree for the case.

After each assessment, `reports/completed_case_damage_tree_assessments.md` is rebuilt.
It contains a campaign summary followed by the complete assessment and tree image for
every available completed case. Rebuilding rather than blind text appending prevents
duplicate sections when a case is reassessed.

## PDF propagation rules

* A system is severe when at least one major item is severe.
* A system is moderate when at least one major item is moderate, or a secondary item
  is severe, and no major item is severe.
* A system is mild when at least one mapped item is mild and no higher rule is met.
* The aircraft level is the highest known level among airframe, avionics, power and
  cockpit systems.
* Missing probe evidence remains unknown and is never treated as undamaged.

## H1-H5 mapping

| Model group | PDF/project node | System role | Current temperature-duration criteria |
|---|---|---|---|
| H1 | Navigation subsystem | Avionics major | 120 C/300 s; 250 C/180 s; 400 C/5 s |
| H2 | Mission subsystem, model-specific mapping | Avionics major | Generic electronics criteria: 120 C/300 s; 250 C/180 s; 400 C/5 s |
| H3 | Display subsystem, model-specific mapping | Cockpit major | Generic electronics criteria: 120 C/300 s; 250 C/180 s; 400 C/5 s |
| H4 | Communication subsystem | Avionics secondary | 120 C/300 s; 250 C/180 s; 400 C/5 s |
| H5 | Battery | Power major | 100 C/60 s; 150 C/600 s; 200 C/180 s |

H1, H4 and H5 have same-name PDF criteria. H2 and H3 are explicit project mappings
because the PDF does not provide same-name rows for the updated model. The report marks
this limitation rather than presenting those mappings as direct quotations from the
standard.

H1-H4 currently use aluminium-enclosure wall temperature as a proxy for internal
electronics temperature. This remains a modeling limitation and is stated in every
case report. A future internal-component or equivalent thermal-network model can replace
the proxy without changing the tree reporting interface.

## Two non-equivalent outcomes

`aircraft_level=severe` follows the PDF: one severe aircraft system is sufficient for
severe aircraft-target damage. `all_severe=true` requires every one of the 17 monitored
groups to be severe. Threshold-search conclusions must state both values because a case
can satisfy the PDF aircraft-level criterion without satisfying the 17/17 objective.

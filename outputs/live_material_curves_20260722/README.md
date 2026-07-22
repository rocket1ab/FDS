# Live material curves, 2026-07-22

This snapshot compares the currently running audited-thickness Q100 and Q200 cases
with the preserved old-thickness Q400 case. At capture time, their simulation times
were approximately 56 s, 233 s, and 1412 s respectively.

## Figures

- `material_temperature_envelopes`: maximum wall-temperature envelope across all
  valid probes assigned to each material/equipment group.
- `material_net_surface_heat_flux_envelopes`: maximum measured net surface heat-flux
  envelope across the same probes. This quantity is not HRRPUA.
- `whole_domain_hrr`: FDS whole-domain HRR output, including a first-300-s view.
- `nominal_material_hrrpua_inputs`: prescribed maximum `HRRPUA` values from the
  current `SURF` definitions. These are model inputs, not time-resolved measurements.

The current FDS inputs do not write material-resolved actual HRRPUA histories. The
available `_hrr.csv` contains whole-domain HRR, while `_devc.csv` contains wall
temperature and net surface heat flux. Material-resolved heat release must be added
as an explicit output design in future cases and cannot be reconstructed uniquely
from the current files.

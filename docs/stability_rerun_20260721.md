# FDS stability rerun record (2026-07-21)

## Finding

The archived Q400 case was not a completed stable run. It had no
`STOP: FDS completed successfully` record and was externally stopped at
193.18 s. Immediately before termination, the maximum divergence in the aft
meshes had already reached approximately 67 to 78. The H1-H7 v2 cases failed
at 176.87 to 179.09 s with the same aft-mesh divergence pattern. The evidence
therefore does not support a geometry-only regression in the updated model.

The former `Q_RAMP` was a global simulation-time ramp. It reached unity during
the first seconds of the run, long before thermally activated surfaces ignited
near 170 s. Delayed ignition therefore still introduced an immediate jump to
full HRRPUA. This is a common trigger for the pressure/divergence growth seen
in both generations of the model.

## Stable v3 changes

The stable cases are stored under `cases_stable` and do not overwrite v2.

1. Peak HRRPUA, ignition temperatures, material properties, external flux,
   fluence, yield and incident angles remain unchanged.
2. Combustible surfaces use `TAU_Q=10.0 s` so heat release grows after actual
   ignition. The obsolete global `RAMP_Q` assignment is removed.
3. `TIME` uses `DT=0.002 s`.
4. `MISC` uses `CFL_MAX=0.5` and `CHECK_HT=.TRUE.`.
5. Density clipping and up to 100 pressure iterations are enabled.
6. `BURN_AWAY` remains false, avoiding geometry changes during this threshold
   campaign.

FDS 6.9.0 requires `CFL_MAX` on `MISC`, not `TIME`. The remote preflight now
changes only `T_END`, preserving and validating all numerical controls.

## Queue allocation

Node 03 was not used because its load was approximately 103 and SSH was
intermittent. The idle node 05 temporarily took its queue.

| Node | Sequential cases |
|---|---|
| node05 | Q50, Q200, Q400 J/cm2 |
| node04 | Q100, Q300 J/cm2 |

Each node runs one 32-process FDS case at a time. A case is assessed only when
the log contains `STOP: FDS completed successfully` and does not contain
`Numerical Instability`.

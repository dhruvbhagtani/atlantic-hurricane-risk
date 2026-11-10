# Wind and loss benchmark

Predeclared sensitivity experiments; no parameters are fitted and no winning model is selected.
Current report peaks are development diagnostics. A test split records event separation,
but does not establish independence from NHC best-track construction or prior analyst use.

| Variant | Step (min) | Station RMSE (m/s) | Bias (m/s) | Insured AAL | AAL change vs baseline |
|---|---:|---:|---:|---:|---:|
| baseline | 1 | 13.70 | 9.91 | $532,088 | +0.00% |
| baseline | 5 | 13.59 | 9.85 | $511,514 | +0.00% |
| baseline | 30 | 13.22 | 9.46 | $416,633 | +0.00% |

Convergence thresholds: maximum property wind change ≤ 1 m/s and absolute
percentage loss-metric change ≤ 1% relative to the finest tested timestep.
A zero reference loss passes only if its absolute change is zero; percentage change is missing.
0 of 18 non-reference metric comparisons pass both thresholds.
These are user-set numerical criteria. The finest timestep is a reference, not proof of convergence.
Return losses use exact annual empirical quantiles, preserving zero years; no annual resampling noise is introduced.
Losses use the full configured hurricane catalog and fixed exposure/policy terms; station skill uses source windows.
Fallback-RMW variants change missing RMW only. Observed positive RMW is preserved.
Track-side and distance diagnostics are geometric. Inland distance is unavailable without an audited coastline.
The prior wind envelope remains an assumed parameter ensemble, not a calibrated predictive interval.
No claim validation, physical climate attribution, or high-wind validation follows from these comparisons.

![Benchmark comparison](benchmark.png)

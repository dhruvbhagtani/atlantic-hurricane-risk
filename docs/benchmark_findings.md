# Historical benchmark findings

These runs use the pinned 1980–2024 HURDAT2 catalog, the original 300-property
synthetic portfolio and the original vulnerability and policy assumptions.
They use exact annual empirical loss quantiles, with no Monte Carlo EP noise.

| Baseline timestep | Insured AAL | Change relative to 1-minute result |
|---|---:|---:|
| 30 minutes | $416,633 | −21.70% |
| 15 minutes | $466,359 | −12.35% |
| 5 minutes | $511,514 | −3.87% |
| 1 minute | $532,088 | reference |

The 5-minute result still differs from 1 minute by up to 2.45 m/s at an
event/property pair, and 3.87% in AAL. It fails the declared 1 m/s and 1% criteria.
The 1-minute case is the finest tested reference; convergence below one minute
has not been established. The production timestep has not been changed silently.

Finer sampling raises baseline station RMSE from 13.22 to 13.70 m/s. Thus improving
numerical resolution does not resolve the observational wind bias. Coarse sampling
can partly obscure overprediction. Do not choose a coarse timestep by station RMSE.

Fallback-RMW and outer-decay variants are individual sensitivity experiments,
not calibrated replacements. At 5 minutes the 25-km fallback lowers AAL by 11.35%,
whereas at 30 minutes it lowers AAL by only 2.83%. Model ranking and loss
sensitivities can themselves depend on timestep; evaluate numerical stability
before interpreting structural parameter comparisons.

The archived reports retain pairwise diagnostics, annual/event losses and manifests:

- [Wind variants](../reports/wind_variants/report.md)
- [Baseline timestep convergence](../reports/timestep_convergence/report.md)

Reproduce into new output directories:

```bash
python -m hurricane_risk.benchmark --out outputs/reproduce-wind-variants
python -m hurricane_risk.benchmark --variants examples/baseline_variant.json \
  --timesteps 30 15 5 1 --out outputs/reproduce-convergence
```

All existing observations remain development diagnostics. A larger quality-controlled
collection remains pending acquisition; see the observational protocol. Absolute
insured losses and hurricane-force wind skill remain unvalidated.

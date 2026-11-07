# Hurricane wind footprint validation

**Finding.** The unchanged Rankine model overpredicts eligible reported station peaks by 9.5 m/s on average (RMSE 13.2 m/s); its assumed 90% wind envelope covers 18% of observations. This external comparison reveals poor agreement but cannot certify an independently withheld wind field. The damaging hurricane-force core remains unvalidated.

## Data and comparability

All 49 unique METAR rows from three preselected NWS regional reports are retained: Irma (2017), Michael (2018), and Ian (2022). 22 station/event pairs have a finite sustained wind, no incomplete flag, and no flagged coordinate issue; only these enter primary scores. Selection uses report membership and quality flags, never the model residual. One duplicate KRSW entry in Irma is removed. All excluded rows and reasons remain in `station_pairs.csv`.

The reports specify 10-m, two-minute sustained winds in knots. The model predicts one-minute sustained winds; conversion to m/s is 0.514444. Following NOAA's duration guidance, the nominal comparison uses no 1-to-2-minute conversion. A hypothetical +5% adjustment of observations is reported separately as duration sensitivity, not a published conversion. Gusts, marine sites, and unknown-height non-METAR measurements are excluded. The same production wind engine and configured 0.85 exposure factor are used at station coordinates; regional UTC passage windows are listed in the provenance JSON. This evaluates peak amplitude at sparse locations, not a complete two-dimensional footprint, gust field, time evolution, or peak timing.

Eligible observed peaks span 9.8–27.8 m/s, all below the 64-kt hurricane threshold. The excluded and censored records contain the strongest measurements, so primary scores cannot establish performance where the vulnerability curves generate the most damage.

These observations were not used to select the original model coefficients. However, NHC may have used the same station data in HURDAT2 intensity analysis. Independence from best-track construction cannot be established; leave-one-storm-out fitting below only prevents leakage in the new multiplicative correction. All three storms are development diagnostics, not an untouched future test set.

## Performance

Errors are modeled minus observed wind, in m/s. Correlation measures association, not agreement. The open-exposure diagnostic divides the nominal wind by 0.85 without fitting, since airport exposure differs from insured properties. No model coefficient is changed by this validation.

| Sample / comparison | n | Bias | MAE | RMSE | Correlation |
|---|---:|---:|---:|---:|---:|
| pooled / nominal | 22 | 9.46 | 9.58 | 13.22 | 0.16 |
| pooled / open_exposure | 22 | 14.22 | 14.22 | 17.72 | 0.16 |
| AL092022 / nominal | 6 | 16.90 | 16.90 | 21.71 | 0.37 |
| AL092022 / open_exposure | 6 | 22.14 | 22.14 | 27.39 | 0.37 |
| AL112017 / nominal | 9 | 5.71 | 6.01 | 7.21 | 0.38 |
| AL112017 / open_exposure | 9 | 10.54 | 10.54 | 11.66 | 0.38 |
| AL142018 / nominal | 7 | 7.91 | 7.91 | 8.84 | 0.45 |
| AL142018 / open_exposure | 7 | 12.16 | 12.16 | 12.99 | 0.45 |
| pooled / observations_plus_5pct_duration_sensitivity | 22 | 8.59 | 8.92 | 12.67 | 0.16 |
| pooled / leave_one_storm_out_correction | 22 | -0.65 | 5.89 | 8.49 | -0.07 |
| pooled_without_Ian / nominal | 16 | 6.67 | 6.84 | 7.96 | 0.52 |

The `pooled_without_Ian` row is a report-quality sensitivity: it omits the entire Ian product because that preliminary summary documents widespread outages. This tests whether the result depends only on unflagged Ian rows; it is not an alternative primary sample selected by error size.

## Uncertainty and transfer test

Resampling whole storms with replacement (2,000 replicates, seeded) gives descriptive 5–95% ranges: bias 6.32 to 13.59 m/s, MAE 6.54 to 13.59, and RMSE 7.70 to 18.07. With only three storms there are very few independent blocks; these coarse ranges are not well-calibrated population confidence intervals. Repeated stations across storms create additional dependence that this storm-only bootstrap does not resolve.

The original assumed model envelope (RMW ×0.8/1.0/1.2 with weights .25/.50/.25, mean-one lognormal intensity with log SD .05) contains 18.2% of eligible observations in its nominal 90% interval. This is an ensemble of model-parameter assumptions, not a predictive interval including observation error or structural discrepancy. Its coverage diagnoses the adequacy of the prior wind uncertainty only; vulnerability uncertainty does not affect wind validation. The 5-minute time-step check changes eligible nominal peaks by at most 4.57 m/s.

A storm-balanced geometric-mean observed/model ratio is 0.629; its three-storm bootstrap factor range is 0.527–0.750. For each held-out storm, a factor fitted only to the other two storms is applied to its station predictions. Held-out pooled RMSE is 8.49 m/s versus nominal 13.22 m/s. A global correction cannot fix storm-size errors, asymmetry, station-specific exposure, or premature sensor failure. It remains diagnostic and is not installed as a calibrated model.

There are 24 finite, metadata-eligible incomplete station peaks, treated only as lower bounds: the model maximum falls below 0 of them. Model excess above an incomplete peak is not evidence of overprediction. Irma KFMY and Ian KVDF coordinates are flagged as suspect rather than silently corrected. Ian report remarks identify more incomplete stations than individual row flags. Unflagged rows can still have outages or report errors; the strongest near-eye winds are especially underrepresented in primary scores.

## Implications for insured losses

The existing 1980–2024 catalog, seeded Florida portfolio, vulnerability curves, deductibles and limits are rerun with global wind multipliers. Below, `empirical_p05/p95` are the wind-factor bootstrap endpoints and `empirical_fit` uses all eligible observations. These are conditional transport sensitivities, not validated loss corrections or total loss uncertainty bounds. Return losses use exact annual empirical CDFs here (the main workflow uses resampled years for scenario EPs).

| Wind sensitivity | Multiplier | Insured AAL | Change | 20-year OEP loss | 20-year AEP loss |
|---|---:|---:|---:|---:|---:|
| nominal | 1.000 | $416,633 | +0.0% | $1,569,109 | $1,641,747 |
| wind_minus_10pct | 0.900 | $225,569 | -45.9% | $652,068 | $652,068 |
| wind_plus_10pct | 1.100 | $680,246 | +63.3% | $2,664,678 | $2,958,472 |
| empirical_p05 | 0.527 | $663 | -99.8% | $0 | $0 |
| empirical_fit | 0.629 | $14,890 | -96.4% | $0 | $0 |
| empirical_p95 | 0.750 | $67,114 | -83.9% | $120,189 | $120,189 |

Nonlinear damage curves and deductibles amplify wind errors: a wind-bias adjustment must be passed through property damage and policy terms, not multiplied directly into AAL. The empirical factor combines wind structure, airport exposure and observation deficiencies; transporting it to residential properties over 45 years is unverified. The original loss model remains unchanged, and its 5% log-SD wind uncertainty assumption should not be interpreted as validated by this experiment.

## Limitations and next scientific step

The narrow sample spans only three regional landfalls and sparse airport locations, with many high-wind instruments censored. Preliminary reports are not full quality-controlled time series. Coordinate precision, one- versus two-minute duration, unresolved exposure, and sensor outages confound model errors. Fixed missing RMW, symmetric radial decay, no terrain and no explicit inland boundary-layer decay remain structural limitations. Wind verification cannot validate assumed damage curves or actual insurance recoveries.

The next step is a locked multi-event test set of quality-controlled station time series with instrument uptime, site exposure and best-track provenance, followed by size/asymmetry diagnostics. Obtain confirmation that those data were withheld from any model fitting and document possible use by NHC. Fit any richer wind model on separate events and evaluate it on the locked storms before replacing the existing loss model.

## Reproduce and audit

```bash
python -m hurricane_risk.validation
python -m unittest discover -s tests -v
```

Inputs, source URLs, QC decisions, observation and track hashes, configuration, software versions and code hashes are retained in `manifest.json`. Pairwise residuals, exclusions, leave-one-storm-out predictions, bootstrap replicates, metric tables and loss sensitivities are adjacent CSVs. `validation_diagnostics.png` visualizes nominal errors, held-out correction errors and conditional AAL sensitivity. `observed_footprints.png` overlays station peaks on modeled geographic footprints using one wind color scale. White lines are best tracks; scalloping near the eye reflects the configured 30-minute sampling.

![Wind validation diagnostics](validation_diagnostics.png)

![Modeled footprints and observed station peaks](observed_footprints.png)

Sources:

- [NWS Tampa Bay PSHTBW, 2017-09-14 16:41 UTC](https://mesonet.agron.iastate.edu/wx/afos/p.php?e=201709141641&pil=PSHTBW) — A. METAR observations; all 10 unique rows, duplicate KRSW removed.
- [NWS Tallahassee PSH, 2018-10-27 01:40 UTC](https://www.weather.gov/tae/michael_psh) — A. METAR observations; all 25 rows; I on maximum sustained wind means incomplete.
- [NWS Tampa Bay PSHTBW, 2022-10-12 18:02 UTC](https://mesonet.agron.iastate.edu/wx/afos/p.php?e=202210121802&pil=PSHTBW) — A. METAR observations; all 14 rows; remarks override individual flags for RSW PGD SRQ SPG TPA GIF PIE.
- [NOAA sustained-wind duration guidance](https://www.aoml.noaa.gov/hrd/tcfaq/D4.html).

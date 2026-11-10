# Current results and reproduction

The remaining wind-model comparisons, coastal diagnostics, reserved-event
protocol and finer numerical checks are implemented and evaluated. The default
now uses one-minute sampling and synthetic land-only exposure. Optional structural
coefficients remain disabled; no model is promoted using test-set errors.

## Defaults and numerical evidence

| Setup | Historical insured AAL |
|---|---:|
| Archived 30-minute configuration, original coordinates | $416,633 |
| Original coordinates, one minute | $532,088 |
| Current land-only coordinates, one minute | $524,813 |
| Current land-only coordinates, 15-second reference | $528,411 |

For current exposure, one-minute AAL differs from the 15-second reference by
0.68%, and the maximum event/property wind difference is 0.73 m/s. All configured
AAL and return-loss comparisons meet the declared 1% loss and 1 m/s wind criteria.
This tests numerical resolution under interpolated tracks, not unobserved storm
evolution. The original exposure also passes at one minute against 15 seconds.

The location correction preserves property IDs, values, construction and policy
terms. It relocates 169 points to satisfy a 2-km inland buffer, including 85 points
originally mapped offshore. Maximum displacement is 10.67 km. Generalized coastline
classification is not parcel verification. The old configuration remains available
and its summary, annual-loss, uncertainty and scenario-comparison tables reproduced
exactly in the final regression run.

## Reserved observations and structural comparisons

Debby and Milton at Valdosta were reserved before inspecting their station-series
winds or errors. Their 260 supported good-QC samples are separate from the existing
Idalia/Helene development series. Original three-event peak diagnostics remain
development observations. These are project-level held-out tests; possible use of
the same station data in NHC best-track analysis is unknown.

| Fixed candidate | Reserved storm-mean bias (m/s) | Reserved storm-mean RMSE (m/s) |
|---|---:|---:|
| Baseline | +5.64 | 6.32 |
| Missing RMW fallback 25 km | +5.64 | 6.32 |
| Translation asymmetry | +4.48 | 5.34 |
| Local inland attenuation | −1.24 | 3.35 |
| Combined structure | −1.67 | 3.68 |

Every candidate was fixed in the reservation and all outcomes are retained.
Scores at one airport and two events do not identify a universally suitable model.
Nominal instrument height and duration are documented; site roughness and continuous
uptime remain unresolved. Report-time scoring never fills an outage or promotes a
censored sampled peak into a complete event peak. Wind-bin, exposure and coordinate
sensitivities are archived with the study.

The full historical structural comparison uses identical original exposure and
one-minute resolution for every candidate. Smaller batches retain completed
results; aggregation requires every repeated baseline table and exposure file to
match exactly. Inland-distance bins and a near-shore uncertainty flag are included.

A separate Laura/Lake Charles high-wind confirmation was registered after the
initial reserved tests, with unchanged candidate parameters. The manually downloaded
2020 CSV and HOMR history now pass validation. Dated ASOS metadata selects surface
record NCDC 20008735 from three returned records, excluding radar and upper-air records.
The [completed Laura confirmation](../reports/laura_confirmation/report.md) retains
71 eligible reports, including four at or above 64 kt and a sampled peak of 43.8 m/s.

| Fixed candidate | Overall RMSE (m/s) | Hurricane-force RMSE (m/s; 4 reports) |
|---|---:|---:|
| Baseline | 8.78 | 16.34 |
| Missing RMW fallback 25 km | 7.14 | 15.40 |
| Translation asymmetry | 8.12 | 15.79 |
| Local inland attenuation | 4.98 | 17.59 |
| Combined structure | 4.90 | 17.94 |

The baseline high-wind signed bias is only −0.42 m/s because large positive and
negative residuals cancel. Inland attenuation improves overall scores but worsens
high-wind RMSE and produces −12.96 m/s high-wind bias. Good reports occupy only
32 of 73 planned cadence bins; the maximum gap including window boundaries is
2,460 minutes. These are report-time scores with an incomplete peak, not validation
of a continuous high-wind footprint. Candidates remain experimental and unchanged.
The separate [NWS reported-point check](../reports/laura_reported_point_check/report.md)
is retained as an earlier diagnostic with a different reported time and coordinate.

## Reproduce

Use fresh output directories: completed experiments cannot be overwritten.

```bash
# Current default; no network needed when the pinned catalog is present.
python -m hurricane_risk --out outputs/current-default-run2

# Original 30-minute result, preserved explicitly.
python -m hurricane_risk --config examples/legacy_30min_config.json \
  --out outputs/legacy-run2

# Frozen Debby/Milton study, using the user's downloaded 2024 annual file.
python -m hurricane_risk.structural_study --out outputs/reserved-study-run2

# Numerical reference with the current land-only exposure.
python -m hurricane_risk.benchmark --variants examples/baseline_variant.json \
  --timesteps 1 0.5 0.25 --out outputs/current-resolution-run2

# Additional registered high-wind confirmation; inputs are now available locally.
bash scripts/download_laura_validation.sh
# For manual downloads, validate both files without network access:
bash scripts/download_laura_validation.sh --check-only
python -m hurricane_risk.confirmation_study --out outputs/laura-confirmation-run3

python -m unittest discover -s tests -v
```

The offline suite contains 54 tests, including registered station/storm weighting,
missing/ineligible pair retention, identity amendments, timing-shift direction and shared
support, inventory missingness, new-collection locks, identity checks that omit
wind values, dated surface-station selection,
interrupted-download cleanup,
input validation and reuse without overwrites, unchanged test-data influence on
development scores, registration/input/model hash checks, land constraints,
shared wind-kernel consistency and CLI financial invariants. Dependency versions
are pinned and GitHub Actions executes the same offline suite. Run source hashes
are now captured before computation so long-run manifests do not pick up later
source edits.

The November 10 continuation completed Laura validation after manual input delivery.
The acquisition command stages and validates each input before publishing it,
preserves existing inputs and offers an offline readiness check. See
[download instructions](data_downloads.md#laura-confirmation-inputs) for exact destinations.

See [the review summary](../reports/final_review/report.md),
[current historical output](../reports/current_default_historical/report.md),
[structural comparison](../reports/structural_models/report.md), and
[reserved study](../reports/reserved_structural_study/report.md).

Absolute insured-loss calibration, continuous high-wind footprints and independence
from NHC input construction are not established by these experiments.

## Timing diagnosis and next collection

The [Laura timing diagnostic](../reports/laura_timing/report.md) reproduces the
archived candidates and shows the baseline dense maximum 33 minutes before the
highest observed report. Center-distance/RMW geometry and all 11 declared timing,
position and size cases are retained without selecting a correction.

The [coverage inventory v3](../reports/observation_inventory_v3/report.md) records
60 examined station/event pairs. Sally, Ida and Florence now supply 1,182 additional
QC report-time comparisons across six stations, with no hurricane-force samples.
Baseline station/storm-balanced RMSE is 4.96 m/s. An event-specific NWS Ida
instrument statement resolves KMSY's height gap via a transparent metadata
supplement after the first evaluation, with every observation and prediction
unchanged. All three storms now have complete nominal instrument eligibility.
All candidates and stations remain in the report. Original test roles are retained;
every examined pair is development-only for future tuning. The original registration,
pre-inspection Wilmington provider-ID amendment, evaluation lock and raw hashes
are preserved. See [the completed collection results](next_collection_results.md).

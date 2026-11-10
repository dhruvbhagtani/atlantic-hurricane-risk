# Atlantic hurricane wind loss workflow

An external station-wind evaluation is now included. See the
[technical validation report](reports/wind_validation/wind_validation_report.md)
for measured model errors, uncertainty coverage and conditional insured-loss
sensitivities. The evaluation exposes substantial wind bias; the high-wind core
and absolute insured losses remain unvalidated.

A runnable Python workflow for a synthetic Florida insurance portfolio, NOAA
Atlantic HURDAT2 tracks, assumed wind and vulnerability models, and paired
historical versus alternative hazard comparisons. All dollar values are assumed
present-day USD with a fixed portfolio. This is an educational catastrophe model;
its assumptions are visible and replaceable, and its losses are not calibrated
to insurance claims.

## Run

Python 3.10+:

```bash
python -m pip install -r requirements.txt
python -m hurricane_risk --download
```

The default download is a pinned NOAA catalog through 2024, not a moving latest
file. The analysis period is 1980–2024 (45 complete years), set in `config.json`.
The downloader validates the format before retaining a file. Existing files are
reused. Alternatively, download [NOAA HURDAT2](https://www.nhc.noaa.gov/data/#hurdat)
yourself and run:

```bash
python -m hurricane_risk --tracks /path/to/hurdat2-atlantic.txt --out outputs/historical
```

Supply the **complete Atlantic catalog**, not selected landfall storms: omitting
storms biases frequency and loss estimates. The parser checks catalog endpoints
but cannot establish completeness of a user-supplied subset. Years are selected
using the storm's season identifier; an event crossing New Year is assigned to
its originating season. Changing to a later end year requires a newer input file.

For an offline integration example:

```bash
python -m hurricane_risk --demo
python -m unittest discover -s tests -v
```

`--demo` fabricates tracks in HURDAT2 format. Its outputs say **FABRICATED DEMO**
and must never be presented as historical hurricane losses. Network access to
NOAA was unavailable in the development workspace; the complete historical run
was validated with a manually downloaded NOAA file. Focused unit tests and
historical output consistency checks passed, including zero-year retention,
AEP >= OEP, and exact AAL scaling with the frequency multiplier.

### Current historical example

The default uses one-minute wind sampling and 300 synthetic locations constrained
to at least 2 km inland in the generalized land dataset. It processes 310 hurricanes
in 1980–2024 and preserves $127,415,900 in replacement value. The location audit
records every relocation; these are synthetic points, not verified insured parcels.

| Scenario | Insured AAL | Combined 5–95% range |
|---|---:|---:|
| Historical | $524,813 | $88,876–$1,058,338 |
| Wind +10% | $821,931 | $200,548–$1,566,439 |
| Wind +10%, frequency +20% | $986,317 | $240,658–$1,879,727 |

The archived 30-minute configuration and original approximate coordinates produced
historical AAL of $416,633. Reproduce that version with
`--config examples/legacy_30min_config.json` and a new output directory. The current
historical run is archived under `reports/current_default_historical/`.

These ranges reflect the assumed model and resampling distributions described
below. RMW is missing for 88.2% of selected track observations, making the assumed
35-km fallback an important source of model dependence. Historical tracks do not
make these uncalibrated wind-only loss estimates observed insurance losses.

## Track and wind model

The [NOAA HURDAT2 format specification](https://www.aoml.noaa.gov/hrd/hurdat/hurdat2-format.pdf)
documents positions, maximum one-minute sustained winds, central pressure and
wind radii. Maximum wind is converted from knots to m/s with factor 0.514444;
RMW is converted from nautical miles to km with factor 1.852. Negative RMW
sentinels are treated as missing. RMW reporting is sparse in historical records.
Missing-wind sentinels (`-99`, also accepting `-999`) are parsed as missing; selected hurricane tracks with
missing intensity stop the workflow rather than silently imputing winds.

Only storms attaining `HU` status somewhere in the selected season are included.
All recorded phases of those storms contribute, including weakening and
extratropical phases; this is an approximation and excludes storms that remain
tropical storms. Original observations, including special landfall fixes, are
retained. Latitude, unwrapped longitude, maximum wind and RMW are interpolated
linearly at one-minute intervals by default. Interpolation smooths the original observations;
it does not reconstruct unobserved rapid intensity changes. Track gaps longer
than 12 hours fail validation. Great-circle distances use Earth radius 6371.0088 km.

The local wind approximation is an **explicitly assumed modified Rankine vortex**:

```
V(r,t) = e * Vmax(t) * r/R(t)             for 0 <= r <= R(t)
V(r,t) = e * Vmax(t) * (R(t)/r)^alpha     for r > R(t)
W(event, property) = max_t V(r(property,t),t)
```

Default `alpha = 0.6`, `e = 0.85`, and missing `R = 35 km`. Observed positive
RMW is used when available. Wind is zero at the center and peaks at RMW; there
is no artificial geographic cutoff. The wind variable throughout is an assumed
one-minute sustained 10-m wind, **not a gust**. `e` is a uniform exposure/roughness
reduction applied to every property, not a geographic land mask or inland decay
model. Observed track intensity already reflects storm weakening to the extent
captured in the best track. The profile ignores translation asymmetry, terrain,
quadrant size, pressure, surface heterogeneity and explicit post-landfall decay;
its outer wind tail is unconstrained by observed wind radii. It is applied to
all phases even though extratropical wind fields may be very different.

Parametric surface wind fitting has a research basis; see
[Knaff et al. (2006), A Real-Time Hurricane Surface Wind Forecasting Model](https://journals.ametsoc.org/view/journals/mwre/134/5/mwr3126.1.xml).
The simple profile and coefficients here are **assumptions**, not a reproduction
or validation of that model or of Holland's pressure-gradient model. A smaller
time step can be used to check peak-wind sensitivity. One-minute sampling passed
the declared 1 m/s maximum wind and 1% loss-metric criteria against 15-second
sampling for both documented synthetic portfolios; this is a numerical check,
not reconstruction of unobserved storm evolution.

## Exposure, damage and policy assumptions

The seeded portfolio contains 300 synthetic properties clustered around Miami,
Tampa, Orlando, Jacksonville, Pensacola and Fort Myers. Seeded coordinate proposals
that fail the 2-km inland buffer are resampled within a fixed region around the
original point. IDs, city labels, construction, replacement values and policy
terms are retained. Locations are approximate city clusters, not verified parcels. Replacement values follow a clipped lognormal distribution
(median $400,000, log standard deviation 0.45, bounds $100,000–$2,000,000).
Construction probabilities are 40% wood, 40% masonry and 20% mitigated.

Mean damage ratios are **explicit assumptions**, linearly interpolated in wind
speed with endpoint clamping:

| Sustained m/s | Wood | Masonry | Mitigated |
|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 |
| 20 | 0 | 0 | 0 |
| 30 | .015 | .005 | .002 |
| 40 | .08 | .04 | .015 |
| 50 | .25 | .15 | .06 |
| 60 | .50 | .35 | .18 |
| 70 | .75 | .60 | .38 |
| 85 | .95 | .85 | .65 |
| 100 | 1 | 1 | .90 |

These are not published FEMA/HAZUS curves. Replacing them with published curves
requires matching their wind averaging duration, height, exposure and building
classes; using a gust-based curve directly with sustained wind would be wrong.
Damage above 100 m/s stays at its last tabulated value. Insurance recovery is
`min(max(value * damage_ratio - 0.02 * value, 0), 1.0 * value)` per property
per event. Both ground-up and insured event losses are saved. Annual losses sum
independent event recoveries, assuming immediate full repair and reinstatement
between storms, with no annual aggregate limit, demand surge, contents, business
interruption, surge, flood or reinsurance.

## AAL, OEP, AEP and alternative scenarios

For each season, sum event insured losses for aggregate loss `A_y`; take the
largest event insured loss for occurrence loss `O_y`. Include every selected
season, including zero-loss years:

- `AAL = sum_y A_y / number_of_years`.
- `OEP(x) = P(O_y > x)` and `AEP(x) = P(A_y > x)`.
- Return loss at period `T` is the inverse empirical CDF at `1 - 1/T`, using
  NumPy's `inverted_cdf` method. Ties and probability atoms need not give exactly
  `1/T` strict exceedance at that loss.

The historical annual catalog is saved directly. EP curves and reported return
losses use 20,000 resampled annual blocks for consistent scenario comparisons;
historical AAL is computed exactly from the original annual catalog, without
simulation error. Blocks retain within-year storm clustering and dependence.

Three scenarios hold tracks, portfolio and policy terms fixed:

1. Historical intensities and frequency.
2. All storm winds multiplied by 1.10, including weakening phases.
3. The same 1.10 wind multiplier plus a 1.20 annual frequency multiplier.

For frequency `f`, a simulated year superposes `floor(f)` independent sampled
catalog years and, with probability `f-floor(f)`, one additional sampled year.
Aggregate losses sum across blocks and occurrence losses take the maximum.
Thus `f=1.2` retains one full annual block and adds another with probability
0.2; the expected event count and AAL increase by 20%. This is an **assumed
annual-block superposition**, not a fitted Poisson frequency model or a physical
climate projection. It changes clustering as well as mean frequency. Values
below 1 produce an inactive year with probability `1-f`. Shared block indices
and random numbers pair scenarios. AAL uses the exact expectation `f * mean(A_y)`.

No return periods longer than the observed catalog are allowed by configuration.
Even the default 20-year loss is weakly constrained by 45 historical years.
Generating 20,000 resampled years does not add storms or identify unobserved
extreme tails. Catalog stationarity is assumed; early observational uncertainty,
historical changes in detection, and secular climate variability are not corrected.

## Uncertainty and comparisons

Each of 200 replicates is run in each of three modes:

- `sampling`: bootstrap 45 annual blocks with replacement; preserve events
  within each sampled year and all zero-loss years.
- `model`: retain catalog years but vary globally shared parameters. RMW
  multiplier is 0.8, 1.0 or 1.2 with probabilities .25, .50 and .25;
  wind intensity has a mean-one lognormal multiplier with log SD .05;
  damage ratio has a mean-one lognormal multiplier with log SD .20, clipped
  to [0,1] after scaling. The RMW alternatives are recalculated wind fields,
  not a monotone size correction to event maxima.
- `combined`: both annual bootstrap and model parameter draws.

Parameters are shared across the whole portfolio and all storms in a replicate,
representing correlated model uncertainty. The same draws and resampled years
are paired across scenarios. Saved intervals are 5th/50th/95th percentiles of
AAL and OEP/AEP return losses. They are conditional sensitivity ranges under
assumed parameter distributions, not calibrated predictive intervals. They do
not include event/property damage randomness, track position errors, exposure
uncertainty, alternative-scenario multiplier uncertainty, or novel storms.
`scenario_comparison.csv` contains paired absolute and percentage changes with
intervals. Percentage changes with a zero baseline are missing; the count of
valid percentage replicates is included. Finite simulation error in EP estimates
is not included as a separate uncertainty component. Increase simulation years
and replicate count to assess numerical stability before relying on estimates.

## Outputs

Every run writes:

| File | Content |
|---|---|
| `report.md`, `summary.csv` | Data label, AAL and return losses |
| `portfolio.csv`, `assumed_vulnerability.csv` | Reproducible exposure and curves |
| `hazard.npz` | Event × RMW alternative × property wind maxima in m/s, with IDs |
| `event_losses.csv` | Ground-up and insured event losses by scenario, before frequency scaling |
| `historical_annual_losses.csv` | Original annual sums/maxima including zero years |
| `historical_empirical_ep.csv` | Exact catalog OEP/AEP at observed loss thresholds |
| `simulated_annual_losses.csv`, `ep_curves.csv` | Simulated annual distributions and strict OEP/AEP |
| `property_aal.csv` | Historical nominal ground-up and insured AAL by property |
| `uncertainty_samples.csv`, `parameter_draws.csv` | Full metric and parameter replicates |
| `uncertainty_intervals.csv`, `scenario_comparison.csv` | Conditional intervals and paired scenario deltas |
| `portfolio_and_ep.png`, `aal_uncertainty.png`, `vulnerability.png` | Figures |
| `manifest.json` | Input SHA-256, source hashes, configuration, versions and missing RMW fraction |

Re-running with the same configuration, file, code and library versions is
seed-reproducible. Completed output directories are protected: a rerun must use a new `--out`.
Runs are staged and published only after successful completion. Synthetic demo outputs default to `outputs/demo`,
while historical runs default to `outputs/historical`.

## Observational validation

```bash
python -m hurricane_risk.validation --out outputs/validation-run1
```

This uses the downloaded HURDAT2 file and the bundled, source-attributed
`data/validation/station_peaks.csv` and `sources.json`. All 49 METAR-section rows
from NWS reports for Irma, Michael and Ian are retained, with 22 eligible primary
comparisons. Incomplete peaks are lower bounds; suspect coordinates and missing
winds are excluded from primary metrics. The command reproduces the report,
diagnostic figure, station matches, exclusions, uncertainty bootstrap,
leave-one-storm-out correction experiment and loss sensitivities in
`reports/wind_validation/`. The original model and loss configuration are unchanged.

Observations are external to this workflow but may have informed NHC best tracks;
strict independence from track construction is not established. All eligible
observed sustained peaks are below hurricane force. This is a documented
observational diagnostic, not validation of a full spatial field or a fitted
loss correction. See the report for the limits on interpreting the results.


## Custom exposure and vulnerability

```bash
python -m hurricane_risk --tracks data/hurdat2-1851-2024-040425.txt \
  --portfolio examples/portfolio.csv --vulnerability examples/vulnerability.json \
  --out outputs/custom-example
```

Portfolio CSVs require unique `property_id`, `lat`, `lon`, `construction`,
`replacement_value_usd`, `deductible_fraction`, and `limit_fraction`. Coordinates,
values, policy fractions and construction membership are validated. Values use
present-day USD. Custom curves require increasing `wind_nodes_ms`, monotone
`damage_nodes` by construction, and `metadata` identifying the source and local
10-m, one-minute sustained winds in m/s. Gust-based or differently exposed curves
must be explicitly converted before import. The example JSON reproduces the
original assumptions; it is not an empirically calibrated replacement.

For the tested Python 3.12 environment, install `requirements-lock.txt`.
GitHub Actions runs the unit tests and an offline CLI integration test, including
custom inputs, repeatability, policy invariants and overwrite protection. Run
manifests include input and output hashes. Existing historical results predate
these workflow safeguards.

## Joint wind and loss benchmark

```bash
python -m hurricane_risk.benchmark --out outputs/benchmark-run1
```

The default compares 30-, 5-, and 1-minute timesteps for the baseline, missing-RMW
fallbacks of 25/45 km, and outer radial exponents of 0.5/0.7. Each change is tested
individually on the same tracks, observations and exposure. Override these with
`--variants examples/benchmark_variants.json` and `--timesteps 1 0.5 0.25`.
Variants are predeclared sensitivity tests; the command does not fit parameters or
select a winner. The original wind-profile coefficients remain the production baseline; structural candidates are optional.

Outputs include pooled and split-specific `station_skill.csv`, auditable
`station_pairs.csv`, residuals grouped by storm, closest-track distance, side,
intensity and RMW availability in `grouped_errors.csv`, exact annual and event
losses, `summary.csv`, `convergence.csv`, a comparison plot and a report. Geometry
is measured at closest approach, not necessarily peak modeled wind. Inland
distance requires an independently audited coastline and is not inferred here.

Each variant's finest tested timestep is its numerical reference. By default,
non-reference cases pass only when maximum event/property wind change is at most
1 m/s and each loss metric changes by at most 1% (adjust with
`--wind-tolerance-ms` and `--loss-tolerance-pct`). A zero reference loss passes
only when the absolute change is zero. These criteria assess numerical stability,
not observational accuracy; add a finer reference to assess residual discretization.
Return losses use exact annual empirical quantiles to remove resampling noise.

Without `--splits`, all observations are labeled development. An explicit JSON
split must assign every observed storm exactly once to `development` or `test`.
Keep new test events separate before tuning; the three existing storms have
already been examined and cannot become an untouched test set by relabeling.
A split does not establish independence from NHC best-track construction.


## Quality-controlled time-series preparation

`python -m hurricane_risk.observations` prepares compatible peak and source files
from normalized, quality-flagged time series and a predeclared event/station plan.
It retains incomplete and missing station records, computes cadence coverage and
maximum gaps, checks wind duration/height/exposure metadata, and verifies registered
plan hashes for test events. See [the observational protocol](docs/observation_protocol.md)
for the schema, commands, data requirements and source-discovery links.

The expanded collection now adds downloaded Idalia and Helene Valdosta records,
with 185 observations passing wind QC. Their sampled peaks are incomplete, and
height and duration are now documented, while roughness and complete uptime remain unresolved; these are development diagnostics.
The peak benchmark retains 51 rows across five storms and 22 eligible primary
comparisons. Debby and Milton were separately reserved before structural development and now
supply 260 test samples. Their report-time scores and metadata audit are retained
in the frozen study; independence from NHC best-track construction is not established.
Prepared time-series outputs should be evaluated with the benchmark command.
The original `hurricane_risk.validation` narrative is specific to the bundled NWS
peak dataset. Both loss and legacy validation commands now accept custom portfolio
and vulnerability inputs and protect existing output directories.

The [historical benchmark findings](docs/benchmark_findings.md) document substantial
timestep sensitivity: baseline insured AAL is $416,633 at 30 minutes, $511,514 at
5 minutes and $532,088 at 1 minute. The 5-minute case still fails the declared
convergence criteria against the 1-minute reference. Archived comparison reports
and provenance manifests are linked there.

For manual NOAA acquisition, see [the station-year download links and import commands](docs/data_downloads.md).
`python -m hurricane_risk.global_hourly` reads the downloaded CSVs, decodes sustained
wind speeds and quality flags, and retains raw event records and a QC audit. Site
exposure and instrument uptime still need separate evidence; height and duration
are documented in the station audit.

[Valdosta time-series diagnostics](reports/valdosta_time_series/report.md) compare
available observations at their reporting times and show the missing data near
the storms. [The expanded peak benchmark](reports/expanded_observations/report.md)
retains the new censored records without treating them as complete event peaks.

## Structural models and reserved events

[Structural-model methods](docs/structural_models.md) describe the translation
asymmetry, local inland attenuation, coastline audit, station metadata and frozen
Debby/Milton evaluation. These candidates are explicit sensitivities and remain disabled in the
production baseline. `examples/structural_config.json` supplies the
versioned coastline; `examples/structural_variants.json` reproduces the registered
candidate list. Fractional-minute timesteps are supported for convergence checks.

The finer coastline audit identifies 85 offshore points in the original synthetic
portfolio. Those approximate coordinates are retained for controlled comparisons;
they must not be interpreted as verified insured parcels. The station metadata
audit now documents Valdosta's nominal 10-m wind height and two-minute duration.
Earlier archived preparation reports preserve their original, more conservative
metadata flags; continuous uptime and quantitative site roughness remain unresolved.


The completed [structural comparison](reports/structural_models/report.md),
[reserved-event evaluation](reports/reserved_structural_study/report.md), and
[subminute convergence checks](reports/subminute_convergence/report.md) retain
all candidate results. The [land-only resolution check](reports/land_only_resolution/report.md)
verifies the current exposure separately. See [current results](docs/current_results.md)
for the resulting default behavior, remaining model limitations and reproduction commands.

The [final review](reports/final_review/report.md) includes a separate
[source-reviewed Laura high-wind point](reports/laura_reported_point_check/report.md).
It reveals strong underprediction at that time, which the inland-attenuation
candidate worsens despite improving the milder Valdosta scores. Optional candidates
remain experimental; the full Laura NOAA time series is still a separate pending input.

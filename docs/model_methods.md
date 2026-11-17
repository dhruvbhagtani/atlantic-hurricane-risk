# Model methods and assumptions

This reference describes the default wind and loss workflow. See the
[README](../README.md) for setup and usage,
[current results](current_results.md) for evaluated defaults, and
[structural-model methods](structural_models.md) for optional candidates.

## Track and wind model

The [NOAA HURDAT2 format specification](https://www.aoml.noaa.gov/hrd/hurdat/hurdat2-format.pdf)
documents positions, maximum one-minute sustained winds, central pressure and
wind radii. Maximum wind is converted from knots to m/s with factor 0.514444;
RMW is converted from nautical miles to km with factor 1.852. Negative RMW
sentinels are treated as missing. RMW reporting is sparse in historical records.
Missing-wind sentinels (`-99`, also accepting `-999`) are parsed as missing; selected hurricane tracks with
missing intensity stop the workflow rather than silently imputing winds.

When `ibtracs_path` is supplied (or `--ibtracs` for the loss CLI), missing
HURDAT2 RMW is supplemented from IBTrACS v04r01 `USA_RMW`. Match by `USA_ATCF_ID`
and exact UTC `ISO_TIME`, convert nautical miles with 1.852, and preserve positive
HURDAT2 RMW. Blank, nonfinite, nonpositive and 999 sentinel radii are excluded.
Spur tracks are excluded and duplicate valid storm/time matches fail. Colon-separated
ATCF aliases are supported. No storm-name matching or nearest-time extrapolation
is used. Unmatched fixes retain the configured fallback before ordinary linear
track interpolation. Special HURDAT2 fixes remain intact.

[NOAA's IBTrACS column documentation](https://www.ncei.noaa.gov/sites/default/files/2025-09/IBTrACS_v04r01_column_documentation.pdf)
defines USA_RMW separately from ROCI and quadrant radii, and cautions that RMW is
only best tracked for NHC from 2021 onward and some historical US landfalls.
Elsewhere it is not reanalyzed. Retain USA_AGENCY and IFLAG in the audit, including
IBTrACS interpolation flags; these are supplementary estimates, not independent
truth. Coverage improvement must be measured for the specific input snapshot;
IBTrACS can contain the same missing information as HURDAT2.

Only storms attaining `HU` status somewhere in the selected season are included.
All recorded phases of those storms contribute, including weakening and
extratropical phases; this is an approximation and excludes storms that remain
tropical storms. Original observations, including special landfall fixes, are
retained. Latitude, unwrapped longitude, maximum wind and RMW are interpolated
linearly at one-minute intervals by default. Interpolation smooths the original observations;
it does not reconstruct unobserved rapid intensity changes. Track gaps longer
than 12 hours fail validation. Great-circle distances use Earth radius 6371.0088 km.

The default configuration uses the **Vmax-normalized cyclostrophic Holland
(1980) radial profile**:

```text
x = (R(t)/r)^B
V(r,t) = e * Vmax(t) * sqrt(x * exp(1-x))  for r > 0
V(0,t) = 0
W(event, property) = max_t V(r(property,t),t)
```

`wind_profile = "holland"`, `holland_b = 1.5`, `e = 0.85`, and missing
`R = 35 km` are the current defaults. The unmodified radial profile peaks at
Vmax exactly at RMW. B controls the width and outer tail and is an assumed
parameter, not fitted to pressure or quadrant radii. The implementation uses log
space to remain finite near the eye. It is the cyclostrophic limit of the Holland
pressure-gradient model, normalized to observed one-minute sustained 10-m Vmax;
it does not solve the full Coriolis-dependent gradient wind or infer pressure.
See [Holland (1980), An Analytic Model of the Wind and Pressure Profiles in
Hurricanes](https://doi.org/10.1175/1520-0493(1980)108%3C1212:AAMOTW%3E2.0.CO;2).
No extra gradient-to-surface conversion is applied to best-track surface Vmax.

The uniform exposure reduction e is an assumption. The current default also
applies a bounded local coastal friction transition, described in
[structural-model methods](structural_models.md#local-inland-attenuation).
Translation, terrain, quadrant structure and surface heterogeneity remain
unresolved by the default.
Best-track intensity already includes observed weakening. There is no radial
cutoff; extratropical phases remain an approximation.

For archived runs, `wind_profile = "rankine"` uses the previous modified Rankine
profile: V/Vmax = r/R inside R and (R/r)^rankine_alpha outside R. Configurations
omitting wind_profile retain this legacy behavior. The shipped config explicitly
selects Holland. Existing reports, observational scores, and timestep convergence
claims describe the old Rankine configuration; they do not validate Holland.
Re-run wind validation, numerical convergence and loss calculations for new results.
The default benchmark includes Holland B=1.0 and B=2.0 sensitivities.

## Exposure, damage and policy assumptions

The seeded portfolio contains 300 synthetic properties clustered around Miami,
Tampa, Orlando, Jacksonville, Pensacola and Fort Myers. Seeded coordinate proposals
that fail the 2-km inland buffer are resampled within a fixed region around the
original point. IDs, city labels, construction, replacement values and policy
terms are retained. Locations are approximate city clusters, not verified parcels.
Replacement values follow a clipped lognormal distribution
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


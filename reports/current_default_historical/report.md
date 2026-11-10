# NOAA HURDAT2 user-supplied or downloaded catalog

Portfolio replacement value: $127,415,900.

| Scenario | Insured AAL | Combined 5–95% range |
|---|---:|---:|
| historical | $524,813 | $88,876–$1,058,338 |
| wind_plus_10pct | $821,931 | $200,548–$1,566,439 |
| wind_plus_10pct_frequency_plus_20pct | $986,317 | $240,658–$1,879,727 |

These are wind-only, assumed-model estimates. Alternative scenarios are sensitivity tests, not climate projections.
Ranges combine annual block resampling with assumed wind, storm-size and vulnerability uncertainty; they are not calibrated confidence bounds.
EP CSVs use strict exceedance; return losses are generalized inverse empirical CDF quantiles.
The simulated years recycle this finite catalog and add no new tail information. See README.md for equations and limitations.

Synthetic locations are constrained to the declared generalized land buffer; they are not verified insured parcels. See exposure_location_audit.csv.

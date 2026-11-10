# Laura reported high-wind point check

The NWS corrected Laura METAR report documents KLCH sustained wind of 85 kt at 06:54 UTC on 27 August 2020.
Its header specifies 10-m height and two-minute averaging. The event peak is explicitly incomplete.
The fixed candidates are compared at that report time, not against a presumed complete event maximum.
The reported value was known when the Laura case was selected; no Laura residuals or station-series values
were used to change candidates. This is a source-reviewed report check, separate from provider-QC time-series validation.

| Candidate | Reported (m/s) | Modeled (m/s) | Signed error (m/s) | Coordinate-grid range (m/s) |
|---|---:|---:|---:|---:|
| baseline | 43.73 | 26.99 | -16.74 | 25.63–28.34 |
| fallback_rmw_25km | 43.73 | 28.47 | -15.26 | 27.04–29.90 |
| translation_asymmetry | 43.73 | 26.39 | -17.34 | 25.06–27.73 |
| local_inland_attenuation | 43.73 | 18.39 | -25.34 | 17.57–19.20 |
| combined_structure | 43.73 | 17.99 | -25.74 | 17.18–18.79 |

The nine-point coordinate grid spans the published coordinate rounding (±0.005 degrees). It is a location
sensitivity, not a predictive interval and not an allowance for unobserved storm-center errors.
One reported high-wind point does not validate a spatial hurricane core, complete event peak or population skill.
The one-minute model and two-minute observation retain the nominal-duration comparison; no conversion is fitted.
Unknown site roughness and station/track uncertainty remain. The requested full NOAA Laura series is still a separate pending input.
No candidate is selected or promoted from this check.

[NWS Laura post-storm report](https://www.weather.gov/lch/2020Laura-PSHLCH).

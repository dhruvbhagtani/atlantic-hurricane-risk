# Structural wind candidates and the reserved-event study

The study registration is `data/validation/reserved_evaluation.json`, committed
before inspecting the Debby and Milton windows in the downloaded Valdosta annual
CSV. Candidate parameters, event windows, station, selection rule and the annual
file hash are fixed there. The subsequent study lock records the implemented
model, coastline and supporting-input hashes before first scoring. The command
rejects changed inputs or model code. No candidate is fitted or selected using
reserved-event errors. Future tuning needs a new test collection.

The original five storms remain development diagnostics. Idalia and Helene supply
the existing development time series; Debby and Milton supply the reserved sample
comparisons. All use the same wind engine and policy/loss code. Being withheld from
this project's fitting does not establish independence from NHC best-track analysis.

## Translation asymmetry

Original fixes determine east/north motion by finite differences in unwrapped
longitude and latitude. Motion components are interpolated to evaluation times.
Let `c` be the cosine between the local cyclonic tangential wind direction and
storm motion, and `U` be translation speed. The radial wind is multiplied by

```text
beta = min(0.25, 0.5 * U / Vmax)
asymmetry_factor = (1 + beta*c) / (1 + beta)
```

Rotation is counterclockwise north of the equator and reverses south of it. This
explicit sensitivity preserves the earth-relative best-track maximum on the
favored side instead of adding storm motion to an already earth-relative Vmax.
It preserves the zero wind at the center and the stationary-storm limit. The
coefficients are declared assumptions, not a fitted or published model reproduction.

## Local inland attenuation

Natural Earth land polygons determine whether a site is on land and its signed
nearest-coast distance. Positive distances indicate inland sites. The wind at the
site is multiplied by `exp(-max(distance_km, 0)/100)`. This is an explicitly assumed
local roughness sensitivity. It does not apply another center-intensity weakening
equation to best tracks that already include weakening. It is not the Kaplan–DeMaria
inland intensity model, and shortest coastal distance is not directional land fetch.
The study compares baseline, missing-RMW fallback 25 km, translation alone, local
inland attenuation alone and their combination.

## Coastline provenance and audit

The regional artifacts derive from Natural Earth land shapefiles: 1:10 million,
version 5.1.1, with 1:50 million version 4.1.0 as a scale-sensitivity comparison.
They retain source SHA-256, projection, bounds, version and license URLs. Coastline
is clipped from the dissolved original boundary; artificial clipping edges are
never used as shoreline. A regional projection identifies the nearest point and
the final distance uses the same spherical Earth radius as the hazard engine.

Both sources are generalized cartographic datasets. They are not parcel surveys.
A diagnostic flag identifies sites within 5 km of shore. The finer layer resolves
the Miami reference point that the coarser layer misclassifies. The site audit
records 38 land/water disagreements across 343 distinct exposure/station sites.
The original synthetic portfolio has 85 points mapped offshore; those points are
retained for direct paired comparisons and clearly flagged, rather than silently
relocated or interpreted as verified insured parcels.

```bash
python scripts/audit_coastline.py --out outputs/coast-audit-run2
python -m hurricane_risk.benchmark --config examples/structural_config.json \
  --variants examples/structural_variants.json \
  --observations data/validation/expanded_station_peaks.csv \
  --sources data/validation/expanded_sources.json \
  --timesteps 1 --out outputs/structural-models-run2
python -m hurricane_risk.structural_study --out outputs/reserved-study-run2
```

## Instrument metadata and scoring

The archived NOAA HOMR response establishes Valdosta's station identifiers,
primary DCP coordinates and sonic wind equipment history. The NIST Idalia
station table documents a 10-m anemometer; NWS documents the two-minute ASOS wind
convention. The NIST wind-site coordinates differ by about 0.7 km from the current
DCP coordinates, so both locations are evaluated as a sensitivity. Height evidence,
source links, dates and hashes are retained in the station metadata audit.
Quantitative directional roughness and continuous uptime are not established.

Report-time metrics use only observations passing the documented provider QC
filter and supported by best-track times. Winds are not interpolated across gaps.
A storm-balanced summary avoids weighting an event solely by its number of reports;
wind-bin counts, paired error changes, exposure factors 0.85/1.0 and coordinate
sensitivity are retained. Two test events at one station cannot establish regional
generalization or high-wind core accuracy. Incomplete sampled peaks remain lower
bounds even when report-time comparisons are useful. Absolute insured-loss
calibration still requires vulnerability and claims evidence.

Sources:

- [Natural Earth land](https://www.naturalearthdata.com/downloads/10m-physical-vectors/10m-land/) and [terms](https://www.naturalearthdata.com/about/terms-of-use/).
- [NOAA HOMR API](https://www.ncei.noaa.gov/access/homr/api).
- [NIST Idalia model-fit report, station table on page 4](https://s3.amazonaws.com/fema-femadata/NationalDisasters/2023/Idalia/NIST_Windfield/Release_1/3-Hurricane_Idalia_2023_Model_Fit_Release1.pdf).
- [NWS ASOS wind measurement convention](https://www.weather.gov/asos/WindSensor.html).

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

The current default uses `inland_profile = "coastal_transition"`. Natural Earth
polygons provide signed nearest-coast distance d (positive on land). The local
wind is multiplied by a bounded surface-friction transition:

```text
s = clip(max(d, 0) / 1.852, 0, 10)    # nautical miles
Q = clip(1 - 0.195*s + 0.0095*s*s, 0, 1)
factor = f_eq + (1 - f_eq)*Q
```

The Q curve and 10-nautical-mile transition come from
[Schwerdt, Ho and Watkins (1979), NOAA Technical Report NWS 23,
section 15.2.4.3, equations 15.2–15.3](https://www.govinfo.gov/content/pkg/CZIC-qc983-n75-no-23/html/CZIC-qc983-n75-no-23.htm).
It describes frictional adjustment toward an equilibrium, separately from
storm filling. We normalize the coastal value to one because the model already
applies `land_exposure_factor`. The assumed equilibrium ratio is configurable
as `inland_equilibrium_factor`, default 0.78/0.89 (about 0.8764), based on the
report's strong-wind land and coast coefficients. This is an adaptation: the
report uses along-wind fetch and 10-minute winds, whereas here nearest-coast
distance approximates fetch and the multiplier is applied to one-minute winds.
The ratio and its use across all wind strengths need observational validation;
they are not a reproduction of the full NOAA model or a fitted site correction.

At the coast and over water the extra factor is one; by 18.52 km inland it
reaches f_eq and remains there. With exposure 0.85, the combined default factor
is about 0.745 far inland. Increasing coastal distance cannot make this local
friction factor vanish. Terrain, flow direction, inland water and changing
roughness remain unresolved. A directional fetch and roughness model would be
needed to resolve those processes. See also
[Vickery et al. (2009), A Hurricane Boundary Layer and Wind Field Model for Use
in Engineering Applications](https://doi.org/10.1175/2008JAMC1841.1) for a more
complete boundary-layer treatment.

Exponential **storm-intensity decay with time since landfall** has an empirical
basis in [Kaplan and DeMaria (1995)](https://rammb-data.cira.colostate.edu/ships/docs/1995_JAM_Kaplan_inland-wind.pdf).
That does not validate the former shortest-distance multiplier
`exp(-max(d,0)/100)`. Applying another storm-intensity decay to HURDAT2 would
repeat weakening already present in its observed Vmax. We do not do so.

For reproducibility, `inland_profile = "exponential"` and positive
`inland_decay_km` retain the former experimental distance exponential;
`inland_profile = "none"` disables the local adjustment. When inland_profile is
omitted, a positive inland_decay_km selects the old exponential, otherwise no
local adjustment is applied. Explicit selection takes precedence. The archived
reserved study below used baseline, fallback RMW 25 km, translation, distance
exponential, and their combination. Its scores do not evaluate the new profile.

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

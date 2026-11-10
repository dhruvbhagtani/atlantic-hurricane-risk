# Observational benchmark protocol

The bundled three-event peak dataset remains a development diagnostic. The new
preparation workflow supports a larger benchmark but does not manufacture new
observations or certify provider quality flags. No additional real time series
were acquired during implementation: direct NOAA requests failed DNS resolution,
and the browsing service could not retrieve the source CSV files. No instrument
uptime, exposure, height or independent-test status has been inferred to fill that gap.

1. Choose events and stations before examining residuals. Include a range of
   landfall regions, intensities, storm sizes and inland distances. Record why
   stations are selected and retain every planned station even if it later fails.
2. Obtain sustained wind time series with quality-control documentation, UTC
   offsets, sampling cadence, instrument height, averaging duration, site exposure
   and instrument uptime logs. Reporting completeness is not proof of sensor uptime.
   Identify whether the observations may have informed NHC best-track analysis.
3. Assign whole storms to development or test. Existing Irma, Michael and Ian
   diagnostics have already been examined; they belong in development. Freeze the
   full event/station plan before evaluating new test events. Registration provides
   an auditable hash and timestamp; it cannot prove nobody inspected the data earlier.
4. Normalize data into `storm_id,station_id,time_utc,sustained_ms,quality_flag`.
   Map provider flags explicitly to `good`, `suspect`, or `missing` and document the
   mapping. Do not label an unchecked archive `good`. The preparation command accepts
   normalized data; it does not silently interpret provider-specific QC codes.
5. Preserve raw files and source citations alongside the normalized series. Run
   preparation and inspect the coverage audit. Missing or suspect winds cannot
   contribute peaks. Incomplete station peaks remain lower bounds.
6. Tune models on development events only. Evaluate predeclared variants on the
   locked events and report every tested candidate, rather than choosing by test RMSE.
   New model tuning after examining tests requires a new untouched test collection.

```bash
python -m hurricane_risk.observations --plan event_plan.json \
  --lock-plan --out data/validation/registered-study
python -m hurricane_risk.observations --plan event_plan.json \
  --registration data/validation/registered-study \
  --series station_time_series.csv --out data/validation/prepared-study
python -m hurricane_risk.benchmark \
  --observations data/validation/prepared-study/station_peaks.csv \
  --sources data/validation/prepared-study/sources.json \
  --splits data/validation/prepared-study/splits.json \
  --out outputs/expanded-benchmark
```

See `examples/observation_plan_template.json` for the plan schema. Its example
storm and instrument records are fabricated schema illustrations, not observational
metadata. Replace every placeholder using source records. `uptime_confirmed` must
be a boolean and have a reference. Unsupported height, duration or unknown exposure
excludes the peak from primary comparisons. For the supported 1- or 2-minute winds,
no duration adjustment is fitted or silently applied.

Coverage counts occupied cadence bins within the event window; bursts of extra
reports cannot compensate for missing intervals. By default, at least 95% of
expected bins, no gap exceeding two reporting intervals, and confirmed instrument
uptime are required for a complete peak. Thresholds are explicit CLI options and
saved to the manifest. Expected reports include the window endpoint when on cadence.
A peak can still be missed between reports; these tests establish eligibility for
a sampled-peak comparison, not continuous peak capture. Calm-only or entirely
missing station records are retained but excluded from primary peak scores.

Source discovery starting points:

- [NOAA NCEI Integrated Surface Database](https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database): station records and quality-control documentation. Verify instrument and averaging conventions per station.
- [NWS Tallahassee Idalia observations](https://www.weather.gov/tae/HurricaneIdalia2023): source reports and downloadable event observations. Summary peaks alone do not establish uptime.
- [NDBC measurement descriptions](https://www.ndbc.noaa.gov/faq/measdes.shtml): averaging conventions differ across station types; marine measurements should not be pooled into the existing airport benchmark without a separate comparison design.

Do not interpret improved station RMSE as insurance-loss validation. Building
vulnerability, policy coverage, repair assumptions and claims require separate data.

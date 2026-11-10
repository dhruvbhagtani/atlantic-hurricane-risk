# NOAA station-year downloads

Start with Valdosta Regional Airport, expected Global Hourly identifier
`72216693845`. These station-year URLs were supplied to the user for manual
retrieval because the execution environment cannot resolve the NOAA download host.
The user supplied both downloads. Their station identifier, Valdosta name, KVLD call
sign, coordinates (30.77629, −83.27393) and year spans have now been verified from
the file contents. Raw annual files are ignored by Git; their hashes and extracted
event records are retained in the normalization manifests.

- [2023 station-year CSV](https://noaa-global-hourly-pds.s3.amazonaws.com/2023/72216693845.csv)
- [2024 station-year CSV](https://noaa-global-hourly-pds.s3.amazonaws.com/2024/72216693845.csv)
- [NOAA Global Hourly archive browser](https://noaa-global-hourly-pds.s3.amazonaws.com/index.html)
- [NOAA ISD data specification](https://www.ncei.noaa.gov/pub/data/noaa/isd-format-document.pdf)

Save the files into different year directories so they do not overwrite each other:

```text
data/raw/global_hourly/2023/72216693845.csv
data/raw/global_hourly/2024/72216693845.csv
```

The reader below normalizes wind records during analyst-selected regional passage
windows. These windows must match the subsequent observation plan. They are not
instrument uptime assertions or automatically verified peak-capture windows.

```bash
python -m hurricane_risk.global_hourly \
  --files data/raw/global_hourly/2023/72216693845.csv \
  --storm-id AL102023 --station-id KVLD --ncei-id 72216693845 \
  --start 2023-08-29T00:00:00Z --end 2023-08-31T23:59:00Z \
  --out data/validation/idalia_valdosta_series
python -m hurricane_risk.global_hourly \
  --files data/raw/global_hourly/2024/72216693845.csv \
  --storm-id AL092024 --station-id KVLD --ncei-id 72216693845 \
  --start 2024-09-25T00:00:00Z --end 2024-09-28T23:59:00Z \
  --out data/validation/helene_valdosta_series
```

The reader uses WND sustained speed, not gust fields. Speeds are decoded in tenths
of m/s. Only speed quality codes `1` and `5` qualify as good; other finite values
are retained as suspect. Missing `9999` speeds remain missing. The conservative
filter also requires METAR/SPECI records, a matching call sign, and normal,
variable or calm wind types. Other averaging durations and wind types remain
suspect. Raw event records and every QC decision are saved beside the normalized
series. Exact duplicate timestamps are collapsed; conflicting values are flagged,
with no choice based on wind magnitude.

Before using `hurricane_risk.observations`, obtain station-specific height,
averaging duration, exposure and uptime documentation, establish cadence from the
reporting protocol, and register the event/station plan. Do not infer those facts
from the existence of an hourly file. Concatenate normalized time-series files
when evaluating multiple events, preserving their storm and station identifiers.
Two events at one station are an initial diagnostic, not a sufficiently broad
independent validation collection. Further events and stations are still required.


The imported windows retain 89 good Idalia samples and 96 good Helene samples.
Their maximum gaps, including the missing ends of the windows, are 2,046 and
2,654 minutes. Instrument uptime and station-specific height/exposure remain
unverified, so these are development diagnostics with incomplete sampled peaks.

```bash
python -m hurricane_risk.time_series_validation \
  --series data/validation/valdosta_time_series.csv \
  --plan data/validation/valdosta_event_plan.json \
  --out outputs/valdosta-timeseries-run2
python -m hurricane_risk.benchmark \
  --observations data/validation/expanded_station_peaks.csv \
  --sources data/validation/expanded_sources.json \
  --variants examples/baseline_variant.json --timesteps 30 5 1 \
  --out outputs/expanded-benchmark-run2
```

Time-matched metrics use actual good report times, with no observed interpolation
across gaps. Model curves stop at the available best-track endpoint. The separate
peak benchmark retains 51 station/event rows across five storms, with the original
22 eligible primary peak comparisons. New data are not promoted to primary scores
without supporting metadata and adequate peak capture.

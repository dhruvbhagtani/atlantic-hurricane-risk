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

## Laura confirmation inputs

The registered Lake Charles/Laura evaluation requires these two files:

- [KLCH 2020 station-year CSV](https://noaa-global-hourly-pds.s3.amazonaws.com/2020/72240003937.csv), saved as `data/raw/global_hourly/2020/72240003937.csv`.
- [KLCH NOAA station history](https://www.ncei.noaa.gov/access/homr/services/station/search?qid=WBAN:03937&date=all&definitions=false&phrData=true), saved as `data/raw/metadata/homr_KLCH.json`.

Run from the project root:

```bash
bash scripts/download_laura_validation.sh
# Validate manually supplied files without network access:
bash scripts/download_laura_validation.sh --check-only
# Once both inputs pass, use a fresh output directory:
python -m hurricane_risk.confirmation_study --out outputs/laura-confirmation-run3
```

The downloader verifies the registered plan and frozen model hashes first. It
checks the CSV schema, station identity, year and event-window records, and the
station history's dated KLCH/WBAN identity and coordinates. Downloads are staged
in temporary files and published only after validation. Interrupted or rejected
downloads are removed; existing files are checked and never overwritten. Move an
invalid existing file aside before retrying. These checks establish usable input
structure, not complete annual coverage or complete event-peak capture.

On November 10, 2026, both files were supplied manually after workspace DNS failures.
Both pass validation. The history returns surface, radar and upper-air records
sharing identifiers; the reader selects the unique dated ASOS surface record.
The [completed evaluation](../reports/laura_confirmation/report.md) retains 71
eligible reports and all five frozen candidates, without tuning or promotion.

## Next registered collection

Sally (KPNS/KMOB), Ida (KMSY/KBTR) and Florence (KILM/KFAY) are now reserved before
their station winds or errors are inspected. The [locked plan](../data/validation/next_collection_v1/plan.json)
lists the six annual CSV and six HOMR URLs and their exact local paths.

```bash
bash scripts/download_next_validation.sh --out outputs/next-inputs-run1
# Check manual downloads without network access; choose a fresh receipt directory.
bash scripts/download_next_validation.sh --check-only --out outputs/next-input-check-run2
```

This command verifies the collection and frozen model hashes, stages downloads,
checks dated surface identity and annual station/year metadata, and records raw
hashes and acquisition times. It excludes wind columns from the annual identity
checks. It does not evaluate candidate errors or certify instrument eligibility.
All 12 files now pass the [offline readiness check](../reports/next_collection_acquisition_v1/receipt.json).
The original KILM URL returned 404; a
[pinned amendment](../data/validation/next_collection_v1/provider_id_amendment_v1.json)
corrects its provider ID to `72302013748`, with
[the corrected CSV URL](https://noaa-global-hourly-pds.s3.amazonaws.com/2018/72302013748.csv)
and local path `data/raw/global_hourly/2018/72302013748.csv`.
The original plan and registration are retained. The six pairs have now been
evaluated under a pre-inspection implementation lock. See
[the completed results and remaining metadata limits](next_collection_results.md).

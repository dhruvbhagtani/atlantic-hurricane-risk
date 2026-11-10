# Timing diagnosis and the next validation collection

The November 10, 2026 milestone delivers a Laura timing diagnostic, a versioned
observation inventory and a new collection registered before its station winds
or errors are inspected. Existing model parameters and frozen source files remain
unchanged. The earlier validation reports retain their original historical claims.

**Completed update:** all six reserved pairs have now been evaluated. The
[collection results](next_collection_results.md) and
[inventory v3](../reports/observation_inventory_v3/report.md) supersede the pending
access/scoring status in the original milestone below. A retained pre-inspection
amendment corrects Wilmington's provider ID to `72302013748`. The new study adds
1,182 QC report-time comparisons and zero hurricane-force reports. KMSY's initial
height gap is resolved by an event-specific NWS statement in a transparent
post-evaluation metadata supplement; observed winds and predictions are unchanged.

## Laura timing evidence

The [timing diagnostic](../reports/laura_timing/report.md) reproduces all five
archived candidates at every eligible report time, then evaluates the same models
at one-minute intervals. Its plots show observed winds, model curves, residuals,
center distance, effective radius of maximum wind (RMW) and long observation gaps.

The baseline's dense maximum is 55.60 m/s at 06:20 UTC, 33 minutes before the
highest observed report, 43.8 m/s at 06:53 UTC. The interpolated center passes
6.90 km from the dated station location at 07:24 UTC. The baseline places the
station inside its effective RMW by the two later hurricane-force reports, giving
large negative residuals after the earlier positive ones. The observed maximum
is a sampled lower bound, so the 33-minute difference is descriptive rather than
an established error in the complete-event peak time.

Eleven cases retain the baseline and one-factor perturbations: model evaluation
time ±15/30 minutes, original track displacement ±10 km east or north, and missing
RMW fallbacks of 25/45 km. All use the same 71 reports. Positive timing offsets
evaluate the model later than the observation. Raw observations are never shifted
or interpolated, and every result is retained in the declared order.

The sign changes and sensitivity to timing/position warrant further investigation;
they do not identify the true track, storm size or correction. No perturbation is
selected, fitted or applied to production. The scalar wind profile's idealized
eyewall and calm-center structure is itself a possible limitation.

## Coverage inventory v1

The [inventory](../reports/observation_inventory_v1/report.md) covers 60
station/event pairs across 11 storms and 47 distinct stations. Of these, 54 pairs
have already been examined and six are newly reserved. Only five pairs have
evaluated provider-QC time series: Idalia, Helene, Debby and Milton at KVLD and
Laura at KLCH. The remaining examined pairs are reported-peak diagnostics.

Each CSV row preserves the original split, current eligibility for future tuning,
available report counts, hurricane-force report counts, cadence coverage, maximum
gap, peak censoring and metadata limitations. Unknown counts stay missing. The
original peak dataset's eligibility flag does not verify station roughness or
instrument height. All examined tests become development-only for any future
tuning; their historical held-out results remain valid under their original lock.

## Newly registered collection v1

The [plan](../data/validation/next_collection_v1/plan.json) and
[registration](../data/validation/next_collection_v1/registration.json) fix these
six station/event pairs and windows:

| Storm | UTC window | Stations | Expected Global Hourly IDs |
|---|---|---|---|
| Sally, AL192020 | September 14–18, 2020 | KPNS, KMOB | 72222313899, 72223013894 |
| Ida, AL092021 | August 28–September 1, 2021 | KMSY, KBTR | 72231012916, 72232013970 |
| Florence, AL062018 | September 12–17, 2018 | KILM, KFAY | 72302013748, 72303593740 |

Each window starts and ends at 00:00 UTC. Selection uses geography and a
coastal/interior station contrast, without viewing these event/station wind values,
completeness or errors. Neither strong winds nor complete observations are guaranteed.
Expected provider IDs must pass dated identity checks before use. The original
plan retains KILM's initial identifier, `72301313748`. A
[dated provider-ID amendment](../data/validation/next_collection_v1/provider_id_amendment_v1.json)
corrects it to `72302013748` after the original URL returned 404. The correction
uses the same station's dated NOAA history; stations, windows, candidates and
scoring rules are unchanged. Acquisition pins the amendment hash and verifies
its original registration and metadata evidence before applying it.

The primary score first computes station/event RMSE, then averages equally across
stations within storms and equally across storms. All candidates use paired sample
support. Secondary metrics retain high-wind counts/errors and peak timing with
censoring. Three storms do not support strong population confidence claims;
any bootstrap must resample whole storms rather than individual reports.

The lock captures model/reader source, configuration, candidates, tracks and
coastline hashes. The verifier pins the registration hash in source and rejects
changed inputs. This is a local project registration, not an external timestamped
preregistration or proof of independence from NHC best-track construction.

Station-specific height/duration, historical ASOS identities/coordinates and
uptime evidence are pending. Keep all declared pairs and report exclusions rather
than substituting stations after seeing winds or scores. Additional candidates
require a dated supplemental code/parameter lock before any new station wind
access, retaining this original registration.

## Commands and outstanding inputs

Run from the repository root, using fresh output directories:

```bash
python -m hurricane_risk.timing_diagnostic --out outputs/laura-timing-run3
python -m hurricane_risk.observation_inventory --out outputs/observation-inventory-v1-run3

# Download the six annual CSVs and six HOMR JSONs, recording an acquisition receipt.
bash scripts/download_next_validation.sh --out outputs/next-inputs-run1

# Or check manually supplied files without network access:
bash scripts/download_next_validation.sh --check-only --out outputs/next-input-check-run2

python -m unittest discover -s tests -v
```

The plan includes all 12 exact URLs and local destinations. Acquisition preserves
existing inputs and validates staged downloads before publishing them. Its checks
read station, date and call-sign columns only, excluding wind measurements, and
record raw hashes and access timestamps. Instrument eligibility and wind QC remain
separate work before scoring. The initial readiness receipt recorded all 12 files
as absent. The first acquisition validated 11 inputs and recorded the original
KILM URL's 404. The [completed offline readiness receipt](../reports/next_collection_acquisition_v1/receipt.json)
now validates all six annual CSVs and six station histories, including the
corrected KILM file. No new-collection station winds have been inspected.
Instrument eligibility review and a frozen evaluation implementation remain
required before scoring; identity readiness does not establish coverage or uptime.

Station identifiers and collection methods are sourced from the
[NOAA station listing](https://vlab.noaa.gov/web/mdl/verif-station-list),
[NOAA ISD metadata catalogue](https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv),
[NOAA ISD specification](https://www.ncei.noaa.gov/pub/data/noaa/isd-format-document.pdf)
and [NWS ASOS wind convention](https://www.weather.gov/asos/WindSensor.html).

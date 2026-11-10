# Sally, Ida and Florence: frozen evaluation

All six registered station/event pairs have now been evaluated with the original
five candidates. The [current report](../reports/next_collection_study_v2/report.md)
retains every station, all candidate scores, QC decisions, observation gaps,
sampled peaks and timing offsets. The [inventory v3](../reports/observation_inventory_v3/report.md)
marks these observations examined; future tuning needs another held-out collection.

## Inputs and metadata

The original Wilmington CSV URL returned 404. The
[pre-inspection amendment](../data/validation/next_collection_v1/provider_id_amendment_v1.json)
corrects its provider ID to `72302013748`, from dated WMO 72302 and WBAN 13748
surface ASOS metadata. The replacement file verifies station/year and KILM call
sign. All 12 current files pass identity checks and have recorded hashes. The
original registration, stations, windows, candidates and scoring rules remain intact.

The instrument audit uses dated HOMR coordinates and station-specific nominal
10-m heights in the [EPA station inventory](https://www.epa.gov/sites/default/files/2016-12/documents/pp2_final_risk_assessment_w_app_11082016.pdf),
PDF pages 160, 165, 168, 171 and 172. Dated ASOS records and the
[NWS reporting convention](https://www.weather.gov/asos/WindSensor.html) support
nominal two-minute sustained duration. Uptime and site roughness remain unverified.

KMSY moved in 2017, after the historical height reference, so the first evaluation
retained it as conditional-only and left the complete primary score unavailable.
The [event-specific NWS Ida report](https://www.weather.gov/lch/2021Ida-PSHLIX)
was subsequently found to document 10-m height and two-minute averaging for its
METAR stations, explicitly including KMSY. A retained
[metadata supplement](../data/validation/next_collection_v1/station_metadata_supplement_v1.json)
resolves nominal instrument eligibility. This documentation was found after the
first scores were inspected; that timing is explicit. The original audit and
[first evaluation](../reports/next_collection_study_v1/report.md) remain unchanged.
No observed wind, modeled prediction, QC decision, candidate or coordinate changes.

## Results and limits

The collection supplies 1,182 good-QC, track-supported report-time comparisons,
including KMSY's conditional comparisons. **None reaches 64 kt.** Every event peak
remains censored because complete uptime is unconfirmed.

| Fixed candidate | Registered station/storm-balanced RMSE (m/s) |
|---|---:|
| Baseline | 4.96 |
| Missing RMW fallback 25 km | 4.38 |
| Translation asymmetry | 4.61 |
| Local inland attenuation | 4.39 |
| Combined structure | 4.27 |

These means weight stations equally within storms, then storms equally. After
the documented metadata supplement, all six pairs meet the nominal instrument
requirements and the primary score is available across all three storms. Its
numeric values equal the original available-case means: observations and
predictions are unchanged. Unknown site roughness still limits interpretation.

| Station/event | Good supported reports | Good hourly-bin coverage | Maximum gap (minutes) | Sampled maximum (m/s) |
|---|---:|---:|---:|---:|
| Sally / KPNS | 135 | 59.8% | 2,375 | 11.3 |
| Sally / KMOB | 173 | 99.0% | 60 | 20.6 |
| Ida / KMSY | 169 | 96.9% | 150 | 27.8 |
| Ida / KBTR | 103 | 67.0% | 1,925 | 16.5 |
| Florence / KILM | 236 | 80.2% | 1,394 | 28.8 |
| Florence / KFAY | 366 | 99.2% | 60 | 19.6 |

Large gaps at KPNS, KBTR and KILM overlap important storm passages. Missing
observations do not establish weak winds or model peak overprediction. This
collection adds lower-wind geographic evidence; the project's four QC
hurricane-force reports still all come from Laura.

No candidate is selected or promoted. Lower conditional average error does not
establish high-wind performance, footprint accuracy or insured-loss calibration.
No confidence interval based on independent individual reports is supplied.

## Reproduction

The [evaluation lock](../data/validation/next_collection_v1/evaluation_lock_v1/evaluation_lock.json)
captures source, metadata and raw hashes before wind inspection. The
[access record](../data/validation/next_collection_v1/evaluation_access_v1.json)
records evaluation time and completed-manifest hash. Archived output hashes verify.
Existing frozen model source and parameters remain unchanged.

```bash
python -m hurricane_risk.collection_study \
  --lock data/validation/next_collection_v1/evaluation_lock_v1/evaluation_lock.json \
  --out outputs/next-collection-study-v1-run2
python scripts/build_observation_inventory_v2.py \
  --study reports/next_collection_study_v2 --out outputs/observation-inventory-v3-run2
python scripts/apply_collection_metadata_supplement.py \
  --out outputs/next-collection-metadata-supplement-run2
python -m unittest discover -s tests -v
```

All 54 offline tests pass, including the identity amendment, weighting order,
missing/ineligible pair handling, QC exclusions and shared candidate support.
Remaining scientific priorities are observations that capture hurricane-force
winds through outages and quantitative site exposure evidence. New stations
or higher-frequency products require a separate prospective protocol.

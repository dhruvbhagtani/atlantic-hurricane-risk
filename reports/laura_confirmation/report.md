# Laura high-wind confirmation

Laura at Lake Charles was registered after Debby/Milton evaluation as an additional high-wind and geographic confirmation.
The reported NWS event intensity was known when selecting this case; station-series values and model residuals were not.
All candidate parameters, model source hashes and coastline remain unchanged from the frozen comparison.
NWS documents 10-m, two-minute METAR winds and explicitly flags the KLCH event peak incomplete.
Scores use good-QC samples at their actual report times. They do not certify a continuously observed peak or full spatial core.
Site roughness remains unknown; exposure and coordinate alternatives are retained without selection.

| Candidate | Samples | Bias (m/s) | RMSE (m/s) |
|---|---:|---:|---:|
| baseline | 71 | 6.49 | 8.78 |
| fallback_rmw_25km | 71 | 4.53 | 7.14 |
| translation_asymmetry | 71 | 5.85 | 8.12 |
| local_inland_attenuation | 71 | 0.92 | 4.98 |
| combined_structure | 71 | 0.49 | 4.90 |

Samples meeting the 64-kt threshold (32.9244 m/s): 4.

| Candidate | High-wind samples | High-wind bias (m/s) | High-wind RMSE (m/s) |
|---|---:|---:|---:|
| baseline | 4 | -0.42 | 16.34 |
| fallback_rmw_25km | 4 | 0.10 | 15.40 |
| translation_asymmetry | 4 | -1.63 | 15.79 |
| local_inland_attenuation | 4 | -12.96 | 17.59 |
| combined_structure | 4 | -13.78 | 17.94 |

A small signed bias can conceal cancellation between overprediction and underprediction; consult RMSE and the sample residuals.
These samples are not independent storm replicates.
The good sampled peak is 43.80 m/s. It remains a lower bound on the complete event peak.
Good reports occupy 32 of 73 planned cadence bins (43.8%).
The maximum gap, including window boundaries, is 2460 minutes; uptime is unconfirmed.
The surface station history is NCDC 20008735, selected by dated ASOS and station identifiers from 3 returned records.
All results, including failures or underprediction, are reported; no candidate is promoted from these scores.
See coverage.csv for outages, qc_audit.csv for exclusions, and the source hashes in manifest.json.

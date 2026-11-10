# Frozen structural-model evaluation

Candidates and the Debby/Milton report windows were registered before their winds or errors were examined.
Idalia and Helene are development events. No candidate is selected, fitted or promoted using reserved-event scores.
The test is held out from this project’s structural development; station data may have informed NHC best tracks.
Nominal 10-m height is documented in the NIST Idalia station table; two-minute duration follows NWS ASOS documentation.
Quantitative site roughness and continuous uptime remain unknown. These are conditional, time-matched sample scores,
not complete-event peak validation, high-wind core validation or insurance-claims validation.

| Variant | Split | Storms | Samples | Storm-mean bias (m/s) | Storm-mean RMSE (m/s) |
|---|---|---:|---:|---:|---:|
| baseline | development | 2 | 185 | 5.85 | 7.03 |
| baseline | test | 2 | 260 | 5.64 | 6.32 |
| fallback_rmw_25km | development | 2 | 185 | 5.85 | 7.03 |
| fallback_rmw_25km | test | 2 | 260 | 5.64 | 6.32 |
| translation_asymmetry | development | 2 | 185 | 4.78 | 5.63 |
| translation_asymmetry | test | 2 | 260 | 4.48 | 5.34 |
| local_inland_attenuation | development | 2 | 185 | -0.37 | 2.37 |
| local_inland_attenuation | test | 2 | 260 | -1.24 | 3.35 |
| combined_structure | development | 2 | 185 | -0.76 | 2.73 |
| combined_structure | test | 2 | 260 | -1.67 | 3.68 |

Each storm has equal weight in the displayed mean errors. Two reserved events at one station do not
establish geographic generalization or well-calibrated population confidence bounds. Wind-bin counts are saved.
Coverage includes end-of-window gaps. No observed wind is interpolated through an outage; incomplete sampled peaks
remain lower bounds. Site exposure factors 0.85 and 1.0 and the documented alternative wind-tower coordinate
are reported separately without selecting either by error size.

Translation asymmetry preserves best-track Vmax on the favored side. Inland attenuation is a declared local
roughness sensitivity based on shortest inland distance; it does not apply another storm-intensity decay to HURDAT2.
Future tuning after viewing this report requires new test events. The reservation, model hashes, input hashes,
coastline provenance and all sample-level predictions are retained alongside this report.

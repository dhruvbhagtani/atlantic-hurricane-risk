# Observation coverage inventory v1

60 station/event pairs across 11 storms; 47 distinct stations.
Every previously examined storm, including the historical test storms, is development-only for future tuning. Original split roles are preserved separately.
Missing counts mean unknown, not zero. A reported event peak cannot supply a count of hurricane-force time-series reports.

| Storm | Pairs | Time-series pairs | Eligible reports | Hurricane-force reports | Status |
|---|---:|---:|---:|---:|---|
| AL042024 | 1 | 1 | 165 | 0 | examined |
| AL062018 | 2 | 0 | unknown | unknown | registered_unexamined |
| AL092021 | 2 | 0 | unknown | unknown | registered_unexamined |
| AL092022 | 14 | 0 | unknown | unknown | examined |
| AL092024 | 1 | 1 | 96 | 0 | examined |
| AL102023 | 1 | 1 | 89 | 0 | examined |
| AL112017 | 10 | 0 | unknown | unknown | examined |
| AL132020 | 1 | 1 | 71 | 4 | examined |
| AL142018 | 25 | 0 | unknown | unknown | examined |
| AL142024 | 1 | 1 | 95 | 0 | examined |
| AL192020 | 2 | 0 | unknown | unknown | registered_unexamined |

The new collection reserves Sally (KPNS/KMOB), Ida (KMSY/KBTR), and Florence (KILM/KFAY).
These six pairs are registered before their winds, completeness or errors are inspected. Height, dated identity/coordinates, roughness and uptime audits remain pending.
No station is promised to observe hurricane-force winds. Keep missing/outage cases in the eventual report rather than substituting stations after inspection.
See inventory.csv for station-level coverage, gaps, metadata issues, original split roles and source references.
This local hash-and-time registration provides project-level separation, not independence from NHC inputs or an external preregistration timestamp.

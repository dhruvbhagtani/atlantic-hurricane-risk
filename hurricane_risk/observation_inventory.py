"""Build a versioned inventory of examined observations and the next reserved collection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .artifacts import output_directory, output_hashes, sha256
from .model import KNOT_TO_MS

COLLECTION = Path('data/validation/next_collection_v1')
REGISTRATION_SHA256 = '5c827f02a0a7114c89cf73b0f3906ef4156d4d543e2450e3778acf9daa9d8327'
SOURCES = [Path('data/validation/expanded_station_peaks.csv'),
           Path('reports/reserved_structural_study/manifest.json'),
           Path('reports/laura_confirmation/manifest.json'),
           Path('reports/reserved_structural_study/coverage.csv'),
           Path('reports/reserved_structural_study/time_matched_pairs.csv'),
           Path('reports/laura_confirmation/coverage.csv'),
           Path('reports/laura_confirmation/time_matched_pairs.csv'),
           COLLECTION/'plan.json', COLLECTION/'registration.json']


def verify_collection(directory=COLLECTION):
    directory = Path(directory)
    if sha256(directory/'registration.json') != REGISTRATION_SHA256:
        raise ValueError('Next-collection registration changed')
    registration = json.loads((directory/'registration.json').read_text())
    if sha256(directory/'plan.json') != registration['plan_sha256']:
        raise ValueError('Next-collection plan changed')
    for name, digest in registration['frozen_inputs_sha256'].items():
        if sha256(name) != digest:
            raise ValueError(f'Next-collection frozen input changed: {name}')
    plan = json.loads((directory/'plan.json').read_text())
    if set(plan['examined_storms_excluded']) & {e['storm_id'] for e in plan['events']}:
        raise ValueError('Examined storms cannot be registered as new tests')
    return plan


def build_inventory(peaks, studies, plan):
    """Keep unknown counts missing and preserve all declared/legacy event-stations."""
    rows = {}
    for peak in peaks.fillna({'metadata_issue': ''}).to_dict('records'):
        key = (peak['storm_id'], peak['station_id'])
        if key in rows:
            raise ValueError(f'Duplicate peak event/station: {key}')
        rows[key] = {'storm_id': key[0], 'station_id': key[1], 'status': 'examined',
                     'historical_role': 'development', 'future_tuning_role': 'development_only',
                     'product': 'reported_peak', 'reports': np.nan, 'good_reports': np.nan,
                     'eligible_reports': np.nan, 'hurricane_force_reports': np.nan,
                     'cadence_coverage': np.nan, 'max_gap_minutes': np.nan,
                     'incomplete_peak': int(peak['incomplete']), 'height_m': np.nan,
                     'averaging_minutes': np.nan, 'uptime_confirmed': False,
                     'roughness_verified': False, 'metadata_issue': peak['metadata_issue'],
                     'legacy_primary_peak_eligible': bool(not peak['incomplete'] and not peak['metadata_issue'] and pd.notna(peak['sustained_kt']) and peak['sustained_kt'] > 0),
                     'source_references': 'data/validation/expanded_station_peaks.csv'}
    for coverage, pairs, source in studies:
        baseline = pairs[pairs.variant.eq('baseline')]
        if coverage.duplicated(['storm_id', 'station_id']).any():
            raise ValueError('Duplicate coverage event/station')
        for audit in coverage.to_dict('records'):
            key = (audit['storm_id'], audit['station_id'])
            group = baseline[baseline.storm_id.eq(key[0]) & baseline.station_id.eq(key[1])]
            good = group[group.sample_eligible]
            if len(group) != audit['reports']:
                raise ValueError(f'Coverage/sample count mismatch: {key}')
            previous = rows.get(key, {})
            rows[key] = {**previous, 'storm_id': key[0], 'station_id': key[1], 'status': 'examined',
                         'historical_role': audit['split'], 'future_tuning_role': 'development_only',
                         'product': 'quality_controlled_time_series', 'reports': audit['reports'],
                         'good_reports': audit['good_reports'], 'eligible_reports': len(good),
                         'hurricane_force_reports': int((good.sustained_ms >= 64*KNOT_TO_MS).sum()),
                         'cadence_coverage': audit['coverage'], 'max_gap_minutes': audit['max_gap_minutes'],
                         'incomplete_peak': audit['incomplete'], 'height_m': audit['height_m'],
                         'averaging_minutes': audit['averaging_minutes'], 'uptime_confirmed': audit['uptime_confirmed'],
                         'roughness_verified': False, 'metadata_issue': audit['metadata_issue'],
                         'legacy_primary_peak_eligible': previous.get('legacy_primary_peak_eligible', False),
                         'source_references': ';'.join(filter(None, [previous.get('source_references'), source]))}
    for event in plan['events']:
        for station in event['stations']:
            key = (event['storm_id'], station['station_id'])
            if key in rows:
                raise ValueError(f'Reserved pair already examined: {key}')
            rows[key] = {'storm_id': key[0], 'station_id': key[1], 'status': 'registered_unexamined',
                         'historical_role': 'test', 'future_tuning_role': 'held_out',
                         'product': 'planned_global_hourly', 'reports': np.nan, 'good_reports': np.nan,
                         'eligible_reports': np.nan, 'hurricane_force_reports': np.nan,
                         'cadence_coverage': np.nan, 'max_gap_minutes': np.nan, 'incomplete_peak': np.nan,
                         'height_m': np.nan, 'averaging_minutes': np.nan, 'uptime_confirmed': False,
                         'roughness_verified': False, 'metadata_issue': station['metadata_status'],
                         'legacy_primary_peak_eligible': False, 'source_references': str(COLLECTION/'plan.json')}
    return pd.DataFrame(rows.values()).sort_values(['storm_id', 'station_id']).reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    plan = verify_collection()
    hashes = {str(p): sha256(p) for p in SOURCES}
    code_hashes = {p.name: sha256(p) for p in Path(__file__).parent.glob('*.py')}
    studies = []
    for base in ['reports/reserved_structural_study', 'reports/laura_confirmation']:
        archived = json.loads((Path(base)/'manifest.json').read_text())
        if output_hashes(Path(base)) != archived['outputs_sha256']:
            raise ValueError(f'Archived study output hashes changed: {base}')
        studies.append((pd.read_csv(Path(base)/'coverage.csv'), pd.read_csv(Path(base)/'time_matched_pairs.csv'), base))
    inventory = build_inventory(pd.read_csv(SOURCES[0]), studies, plan)
    with output_directory(args.out) as out:
        inventory.to_csv(out/'inventory.csv', index=False)
        (out/'schema.json').write_text(json.dumps({
            'schema_version': 1, 'inventory_id': 'observation_inventory_v1',
            'row_key': ['storm_id', 'station_id'],
            'missing_counts': 'Unknown/not collected, never interpreted as zero.',
            'hurricane_force_reports': 'Number of baseline-eligible time-matched reports >=64 kt; not independent storm replicates. Not inferred from reported peaks.',
            'legacy_primary_peak_eligible': 'Eligibility under the original peak curation only; not verification of station roughness, height or complete uptime.',
            'historical_role': 'Original role; examined tests are development-only for any future tuning.',
            'incomplete_peak': 'Original peak flag or latest series audit; unknown for reserved pairs.',
            'metadata_scope': 'Time series use completed study audits; peak-only instrument metadata remain unknown. No raw new-collection winds are read.'}, indent=2)+'\n')
        text = ['# Observation coverage inventory v1', '',
                f'{len(inventory)} station/event pairs across {inventory.storm_id.nunique()} storms; {inventory.station_id.nunique()} distinct stations.',
                'Every previously examined storm, including the historical test storms, is development-only for future tuning. Original split roles are preserved separately.',
                'Missing counts mean unknown, not zero. A reported event peak cannot supply a count of hurricane-force time-series reports.', '',
                '| Storm | Pairs | Time-series pairs | Eligible reports | Hurricane-force reports | Status |',
                '|---|---:|---:|---:|---:|---|']
        for storm, frame in inventory.groupby('storm_id', sort=True):
            series = frame[frame['product'].eq('quality_controlled_time_series')]
            n = str(int(series.eligible_reports.sum())) if len(series) else 'unknown'
            high = str(int(series.hurricane_force_reports.sum())) if len(series) else 'unknown'
            text.append(f'| {storm} | {len(frame)} | {len(series)} | {n} | {high} | {frame.status.iloc[0]} |')
        text += ['', 'The new collection reserves Sally (KPNS/KMOB), Ida (KMSY/KBTR), and Florence (KILM/KFAY).',
                 'These six pairs are registered before their winds, completeness or errors are inspected. Height, dated identity/coordinates, roughness and uptime audits remain pending.',
                 'No station is promised to observe hurricane-force winds. Keep missing/outage cases in the eventual report rather than substituting stations after inspection.',
                 'See inventory.csv for station-level coverage, gaps, metadata issues, original split roles and source references.',
                 'This local hash-and-time registration provides project-level separation, not independence from NHC inputs or an external preregistration timestamp.', '']
        (out/'report.md').write_text('\n'.join(text))
        (out/'manifest.json').write_text(json.dumps({'schema_version': 1, 'inputs_sha256': hashes,
            'code_sha256': code_hashes,
            'outputs_sha256': output_hashes(out)}, indent=2)+'\n')
    print(f'Observation inventory: {args.out}/report.md')


if __name__ == '__main__':
    main()

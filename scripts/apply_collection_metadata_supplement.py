"""Publish a metadata supplement without changing observations, QC, or predictions."""
import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd

from hurricane_risk.artifacts import output_directory, output_hashes, sha256
from hurricane_risk.collection_study import primary_eligibility, summarize, verify_evaluation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('reports/next_collection_study_v1'))
    parser.add_argument('--supplement', type=Path, default=Path('data/validation/next_collection_v1/station_metadata_supplement_v1.json'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    verify_evaluation('data/validation/next_collection_v1/evaluation_lock_v1/evaluation_lock.json')
    original_manifest = json.loads((args.source/'manifest.json').read_text())
    supplement = json.loads(args.supplement.read_text())
    if (output_hashes(args.source) != original_manifest['outputs_sha256']
            or sha256(args.source/'manifest.json') != supplement['original_results_manifest_sha256']
            or sha256(args.source/'station_metadata_audit.json') != supplement['original_audit_sha256']):
        raise ValueError('Original study or metadata audit changed')
    audits = json.loads((args.source/'station_metadata_audit.json').read_text())
    perf = pd.read_csv(args.source/'station_scores.csv', keep_default_na=False, na_values=[''])
    original_perf = perf.copy(deep=True)
    pairs = pd.read_csv(args.source/'time_matched_pairs.csv')
    original_pairs = pairs.copy(deep=True)
    coverage = pd.read_csv(args.source/'coverage.csv')
    for update in supplement['updates']:
        match = next(a for a in audits['station_audits'] if a['storm_id'] == update['storm_id'] and a['station_id'] == update['station_id'])
        match.update(height_m=update['height_m'], averaging_minutes=update['averaging_minutes'],
                     height_matches_event_site=update['height_matches_event_site'],
                     height_source_url=supplement['source_url'], duration_source_url=supplement['source_url'],
                     height_evidence_scope=update['basis'], height_limitation='Event-specific nominal height/duration documented; sensor uptime and site roughness remain unverified.')
        mask = perf.storm_id.eq(update['storm_id']) & perf.station_id.eq(update['station_id'])
        perf.loc[mask, 'primary_eligible'] = primary_eligibility(match) & perf.loc[mask, 'n'].gt(0)
        perf.loc[mask, 'metadata_limitation'] = match['height_limitation']
        pair_mask = pairs.storm_id.eq(update['storm_id']) & pairs.station_id.eq(update['station_id'])
        pairs.loc[pair_mask, 'primary_sample_eligible'] = pairs.loc[pair_mask, 'sample_eligible'] & primary_eligibility(match)
        coverage.loc[coverage.storm_id.eq(update['storm_id']) & coverage.station_id.eq(update['station_id']), 'primary_metadata_eligible'] = primary_eligibility(match)
    unchanged = [c for c in perf.columns if c not in ['primary_eligible', 'metadata_limitation']]
    pd.testing.assert_frame_equal(perf[unchanged], original_perf[unchanged])
    pd.testing.assert_frame_equal(pairs.drop(columns='primary_sample_eligible'), original_pairs.drop(columns='primary_sample_eligible'))
    plan = json.loads((args.source/'effective_plan.json').read_text())
    storm_scores, summary = summarize(perf, plan)
    with output_directory(args.out) as out:
        for file in args.source.iterdir():
            if file.name != 'manifest.json':
                shutil.copy2(file, out/file.name)
        perf.to_csv(out/'station_scores.csv', index=False)
        pairs.to_csv(out/'time_matched_pairs.csv', index=False)
        coverage.to_csv(out/'coverage.csv', index=False)
        storm_scores.to_csv(out/'storm_scores.csv', index=False)
        summary.to_csv(out/'summary.csv', index=False)
        (out/'station_metadata_audit.json').write_text(json.dumps(audits, indent=2)+'\n')
        (out/'metadata_supplement.json').write_text(args.supplement.read_text())
        text = ['# Frozen multistation validation with documented metadata supplement', '',
                'All six registered Sally/Ida/Florence pairs were evaluated with all five original candidates. The first frozen evaluation is retained under reports/next_collection_study_v1.',
                'After that evaluation, the event-specific NWS Ida METAR report was found to document 10-m height and two-minute averaging for KMSY. This resolves the relocated-site eligibility gap.',
                f"[NWS event-specific instrument evidence]({supplement['source_url']}). This metadata supplement was made after seeing the first scores; its timing is explicit in metadata_supplement.json.",
                'Every observed wind, modeled value, QC decision, paired sample comparison, station and window is unchanged. Only metadata eligibility flags and the consequent primary summary availability change.', '',
                '| Candidate | Complete primary storms | Registered station/storm-balanced RMSE (m/s) | Reports | Hurricane-force reports |',
                '|---|---:|---:|---:|---:|']
        for r in summary.itertuples():
            value = f'{r.registered_primary_rmse_ms:.2f}' if pd.notna(r.registered_primary_rmse_ms) else 'unavailable'
            text.append(f'| {r.variant} | {r.primary_complete_storms}/{r.planned_storms} | {value} | {r.eligible_reports} | {r.hurricane_force_reports} |')
        text += ['', 'The primary metric weights stations equally within each storm, then storms equally. All six pairs now have nominal instrument documentation; directional roughness and continuous uptime remain unknown.',
                 'No good-QC supported observation reaches 64 kt. This is lower-wind geographic evidence, not high-wind validation. All event peaks remain censored, including the NWS-marked incomplete KMSY peak.',
                 'No candidate is selected, fitted or promoted. The model one-minute and ASOS two-minute averaging durations remain explicit without a fitted conversion.',
                 'All station scores, high-wind missing subsets, paired changes, peak timing, exclusions and gaps are retained in the CSV files. Reports are not independent storm replicates.', '',
                 '![Frozen model curves and observed reports](time_series.png)', '']
        (out/'report.md').write_text('\n'.join(text))
        (out/'manifest.json').write_text(json.dumps({'schema_version': 2,
            'original_manifest_sha256': sha256(args.source/'manifest.json'),
            'inputs_sha256': {str(args.source/'manifest.json'): sha256(args.source/'manifest.json'), str(args.supplement): sha256(args.supplement)},
            'original_evaluation_lock_sha256': original_manifest['evaluation_lock_sha256'],
            'script_sha256': sha256(__file__), 'numeric_predictions_and_observations_unchanged': True,
            'outputs_sha256': output_hashes(out)}, indent=2)+'\n')
    print(summary.to_string(index=False))


if __name__ == '__main__':
    main()

"""Archive the post-evaluation coverage inventory while preserving the original v1 snapshot."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd

from hurricane_risk.artifacts import output_directory, output_hashes, sha256
from hurricane_risk.observation_inventory import build_inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--study', type=Path, default=Path('reports/next_collection_study_v1'))
    args = parser.parse_args()
    directories = [Path('reports/reserved_structural_study'), Path('reports/laura_confirmation'),
                   args.study]
    files = [Path('data/validation/expanded_station_peaks.csv'),
             Path('data/validation/next_collection_v1/evaluation_access_v1.json')]
    studies = []
    for directory in directories:
        manifest = json.loads((directory/'manifest.json').read_text())
        if output_hashes(directory) != manifest['outputs_sha256']:
            raise ValueError(f'Archived study changed: {directory}')
        files += [directory/'manifest.json', directory/'coverage.csv', directory/'time_matched_pairs.csv']
        studies.append((pd.read_csv(directory/'coverage.csv'), pd.read_csv(directory/'time_matched_pairs.csv'), str(directory)))
    files += [directories[-1]/'station_scores.csv', directories[-1]/'station_metadata_audit.json']
    hashes = {str(p): sha256(p) for p in files}
    inventory = build_inventory(pd.read_csv(files[0]), studies, {'events': []})
    new_scores = pd.read_csv(directories[-1]/'station_scores.csv')
    new_scores = new_scores[new_scores.variant.eq('baseline')]
    inventory['primary_instrument_eligible_in_new_collection'] = pd.NA
    for r in new_scores.itertuples():
        mask = inventory.storm_id.eq(r.storm_id) & inventory.station_id.eq(r.station_id)
        inventory.loc[mask, 'primary_instrument_eligible_in_new_collection'] = r.primary_eligible
        if not r.primary_eligible:
            inventory.loc[mask, 'metadata_issue'] = inventory.loc[mask, 'metadata_issue'].fillna('')+';height_at_relocated_site_unverified'
    series = inventory[inventory['product'].eq('quality_controlled_time_series')]
    version = 3 if args.study.name == 'next_collection_study_v2' else 2
    with output_directory(args.out) as out:
        inventory.to_csv(out/'inventory.csv', index=False)
        schema = json.loads(Path('reports/observation_inventory_v1/schema.json').read_text())
        schema.update(schema_version=version, inventory_id=f'observation_inventory_v{version}',
                      supersedes='reports/observation_inventory_v1',
                      primary_instrument_eligible_in_new_collection='Eligibility under the six-pair collection audit; missing for earlier studies.',
                      state='All 60 pairs have now been examined. No untouched test pairs remain in this inventory.')
        (out/'schema.json').write_text(json.dumps(schema, indent=2)+'\n')
        text = [f'# Observation coverage inventory v{version}', '',
                f'{len(inventory)} examined station/event pairs across {inventory.storm_id.nunique()} storms; {inventory.station_id.nunique()} distinct stations.',
                f'{len(series)} pairs have evaluated QC time series, with {int(series.eligible_reports.sum())} eligible reports and {int(series.hurricane_force_reports.sum())} hurricane-force reports.',
                'The six Sally/Ida/Florence pairs are now examined. Original test roles remain recorded, but every pair is development-only for any future tuning.',
                'This snapshot supersedes v1 without changing the original registration, v1 inventory or held-out study results.', '',
                '| Storm | Time-series pairs | Eligible reports | Hurricane-force reports |', '|---|---:|---:|---:|']
        for storm, group in series.groupby('storm_id', sort=True):
            text.append(f'| {storm} | {len(group)} | {int(group.eligible_reports.sum())} | {int(group.hurricane_force_reports.sum())} |')
        text += ['', 'All four hurricane-force reports remain the Laura samples. The new collection adds none; reported peaks from other stations cannot substitute for QC time-series sample counts.',
                 ('KMSY nominal height/duration are documented by the event-specific NWS report in the retained metadata supplement.' if new_scores.primary_eligible.all() else 'KMSY has a relocated-site height evidence gap and remains conditional-only in the new study.'),
                 'All event peaks are censored by unverified uptime.',
                 'Unknown counts remain missing; no station was substituted or removed because of its wind values, outages or errors.',
                 'See inventory.csv for coverage, gaps, metadata limitations and original/future roles.', '']
        (out/'report.md').write_text('\n'.join(text))
        (out/'manifest.json').write_text(json.dumps({'schema_version': version, 'inputs_sha256': hashes,
            'script_sha256': sha256(__file__), 'outputs_sha256': output_hashes(out)}, indent=2)+'\n')
    print(args.out/'report.md')


if __name__ == '__main__':
    main()

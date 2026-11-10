"""Evaluate frozen structural candidates on development and reserved station reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd

from .__main__ import validate_config
from .artifacts import output_directory, output_hashes, sha256
from .benchmark import validate_variants
from .global_hourly import normalize_global_hourly
from .geography import coast_distances
from .model import read_hurdat
from .observations import prepare_observations
from .time_series_validation import modeled_at_times
from .validation import scores


REGISTRATION_SHA256 = '49b4fd47b83118a24a39f87dbe844880c3d724a9a3d63a9f7f4950eaee0f217b'


def verify_registration(registration, lock, annual, cfg):
    if sha256(registration) != lock['registration_sha256'] or lock['registration_sha256'] != REGISTRATION_SHA256:
        raise ValueError('Reserved event plan changed after registration')
    registered = json.loads(Path(registration).read_text())
    if lock['annual_input_sha256'] != registered['annual_input_sha256']:
        raise ValueError('Lock does not match the annual file registered before testing')
    if sha256(annual) != lock['annual_input_sha256']:
        raise ValueError('Annual observations changed after registration')
    if sha256(cfg['coastline_path']) != lock['coastline_sha256']:
        raise ValueError('Coastline differs from the frozen study')
    for name, digest in lock['model_code_sha256'].items():
        if sha256(Path(__file__).parent/name) != digest:
            raise ValueError(f'Model code changed after the study was frozen: {name}')
    for name, digest in lock.get('support_inputs_sha256', {}).items():
        if sha256(name) != digest:
            raise ValueError(f'Study inputs changed after freezing: {name}')


def compare_candidates(series, plan, tracks, cfg, variants, out, metadata):
    """Score fixed candidates without any fit, selection or observation imputation."""
    validate_variants(variants, cfg)
    _, coverage, _, _ = prepare_observations(series, plan)
    rows, predictions, exposure_rows, coordinate_rows, strata = [], [], [], [], []
    for variant in variants:
        run_cfg = {**cfg, **variant['overrides']}
        for event in plan['events']:
            tr = tracks[tracks.storm_id.eq(event['storm_id'])]
            if len(tr) < 2:
                raise ValueError(f"Missing track {event['storm_id']}")
            first, last = pd.Timestamp(tr.time.min()).tz_localize('UTC'), pd.Timestamp(tr.time.max()).tz_localize('UTC')
            for station in event['stations']:
                frame = series[series.storm_id.eq(event['storm_id']) & series.station_id.eq(station['station_id'])].copy()
                frame['time_utc'] = pd.to_datetime(frame.time_utc, utc=True)
                supported = frame.time_utc.between(first, last)
                frame['modeled_ms'] = np.nan
                frame.loc[supported, 'modeled_ms'] = modeled_at_times(tr, station, frame.loc[supported,'time_utc'], run_cfg)
                frame['residual_ms'] = frame.modeled_ms-frame.sustained_ms
                frame['variant'], frame['split'] = variant['name'], event['split']
                frame['sample_eligible'] = frame.quality_flag.eq('good') & supported
                frame['height_m'], frame['averaging_minutes'] = metadata['height_m'], metadata['averaging_minutes']
                frame['exposure_assumption'] = run_cfg['land_exposure_factor']
                frame['site_roughness_verified'] = False
                coast, _ = coast_distances([station['lat']], [station['lon']], cfg['coastline_path'])
                frame['inland_distance_km'] = max(coast[0], 0)
                good = frame[frame.sample_eligible]
                if good.empty:
                    raise ValueError('No eligible observed samples in a planned event')
                values = scores(good.sustained_ms, good.modeled_ms)
                rows.append({'variant': variant['name'], 'split': event['split'], 'storm_id': event['storm_id'],
                             'station_id': station['station_id'], **values,
                             'good_samples_outside_track': int((frame.quality_flag.eq('good') & ~supported).sum()),
                             'observed_sampled_peak_ms': good.sustained_ms.max(),
                             'modeled_peak_at_good_report_times_ms': good.modeled_ms.max()})
                predictions.append(frame)
                for factor in [.85, 1.]:
                    adjusted = good.modeled_ms*factor/run_cfg['land_exposure_factor']
                    exposure_rows.append({'variant': variant['name'], 'split': event['split'], 'storm_id':event['storm_id'],
                                          'exposure_factor':factor, **scores(good.sustained_ms, adjusted)})
                alternative = metadata['wind_tower_coordinate_sensitivity']
                alt = modeled_at_times(tr, {**station, 'lat':alternative['lat'], 'lon':alternative['lon']}, good.time_utc, run_cfg)
                coordinate_rows.append({'variant':variant['name'],'split':event['split'],'storm_id':event['storm_id'],
                                        'max_abs_wind_change_ms':float(np.max(np.abs(alt-good.modeled_ms))),
                                        'rmse_ms_at_alternative_coordinate':scores(good.sustained_ms,alt)['rmse_ms']})
                bins = pd.cut(good.sustained_ms, [-.001,5,15,33,np.inf], include_lowest=True)
                for label, group in good.groupby(bins, observed=True):
                    strata.append({'variant':variant['name'],'split':event['split'],'storm_id':event['storm_id'],
                                   'observed_wind_bin_ms':str(label),**scores(group.sustained_ms,group.modeled_ms)})
    performance = pd.DataFrame(rows)
    paired = performance.merge(performance[performance.variant.eq('baseline')][['split','storm_id','station_id','rmse_ms','bias_ms']],
                               on=['split','storm_id','station_id'],suffixes=('','_baseline'),validate='many_to_one')
    paired['rmse_change_ms'] = paired.rmse_ms-paired.rmse_ms_baseline
    paired['bias_change_ms'] = paired.bias_ms-paired.bias_ms_baseline
    paired.to_csv(out/'performance.csv',index=False)
    pd.concat(predictions,ignore_index=True).to_csv(out/'time_matched_pairs.csv',index=False)
    pd.DataFrame(exposure_rows).to_csv(out/'exposure_sensitivity.csv',index=False)
    pd.DataFrame(coordinate_rows).to_csv(out/'coordinate_sensitivity.csv',index=False)
    pd.DataFrame(strata).to_csv(out/'wind_strata.csv',index=False)
    coverage.to_csv(out/'coverage.csv',index=False)
    aggregate = performance.groupby(['variant','split'],sort=False).agg(
        storms=('storm_id','nunique'),samples=('n','sum'),storm_mean_bias_ms=('bias_ms','mean'),
        storm_mean_rmse_ms=('rmse_ms','mean')).reset_index()
    aggregate.to_csv(out/'storm_balanced_summary.csv',index=False)
    text=['# Frozen structural-model evaluation','',
          'Candidates and the Debby/Milton report windows were registered before their winds or errors were examined.',
          'Idalia and Helene are development events. No candidate is selected, fitted or promoted using reserved-event scores.',
          'The test is held out from this project’s structural development; station data may have informed NHC best tracks.',
          'Nominal 10-m height is documented in the NIST Idalia station table; two-minute duration follows NWS ASOS documentation.',
          'Quantitative site roughness and continuous uptime remain unknown. These are conditional, time-matched sample scores,',
          'not complete-event peak validation, high-wind core validation or insurance-claims validation.','',
          '| Variant | Split | Storms | Samples | Storm-mean bias (m/s) | Storm-mean RMSE (m/s) |',
          '|---|---|---:|---:|---:|---:|']
    for r in aggregate.itertuples():
        text.append(f'| {r.variant} | {r.split} | {r.storms} | {r.samples} | {r.storm_mean_bias_ms:.2f} | {r.storm_mean_rmse_ms:.2f} |')
    text += ['', 'Each storm has equal weight in the displayed mean errors. Two reserved events at one station do not',
             'establish geographic generalization or well-calibrated population confidence bounds. Wind-bin counts are saved.',
             'Coverage includes end-of-window gaps. No observed wind is interpolated through an outage; incomplete sampled peaks',
             'remain lower bounds. Site exposure factors 0.85 and 1.0 and the documented alternative wind-tower coordinate',
             'are reported separately without selecting either by error size.','',
             'Translation asymmetry preserves best-track Vmax on the favored side. Inland attenuation is a declared local',
             'roughness sensitivity based on shortest inland distance; it does not apply another storm-intensity decay to HURDAT2.',
             'Future tuning after viewing this report requires new test events. The reservation, model hashes, input hashes,',
             'coastline provenance and all sample-level predictions are retained alongside this report.','']
    (out/'report.md').write_text('\n'.join(text))
    return aggregate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration',type=Path,default=Path('data/validation/reserved_evaluation.json'))
    parser.add_argument('--lock',type=Path,default=Path('data/validation/structural_study_lock.json'))
    parser.add_argument('--annual',type=Path,default=Path('data/raw/global_hourly/2024/72216693845.csv'))
    parser.add_argument('--config',type=Path,default=Path('examples/structural_config.json'))
    parser.add_argument('--tracks',type=Path,default=Path('data/hurdat2-1851-2024-040425.txt'))
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    cfg=json.loads(args.config.read_text());validate_config(cfg)
    lock=json.loads(args.lock.read_text())
    verify_registration(args.registration,lock,args.annual,cfg)
    registered=json.loads(args.registration.read_text())
    metadata_path=Path('data/validation/station_metadata/KVLD_audit.json')
    metadata=json.loads(metadata_path.read_text())
    plan=json.loads(Path('data/validation/valdosta_event_plan.json').read_text())
    series=pd.read_csv('data/validation/valdosta_time_series.csv')
    station={**plan['events'][0]['stations'][0], 'height_m':metadata['height_m'],
             'metadata_reference':'data/validation/station_metadata/KVLD_audit.json'}
    for event in plan['events']:
        event['stations']=[station.copy()]
    raw=pd.read_csv(args.annual,dtype=str,keep_default_na=False)
    raw['raw_file']=str(args.annual)
    normalized, audits, raw_events = [], [], []
    for event in registered['test_events']:
        frame,audit,source=normalize_global_hourly(raw,event['storm_id'],station['station_id'],
                                                metadata['ncei_id'],event['start'],event['end'])
        normalized.append(frame);audits.append(audit);raw_events.append(source)
        plan['events'].append({'storm_id':event['storm_id'],'name':event['name'],'split':'test',
                              'window_start':event['start'],'window_end':event['end'],
                              'product':'NOAA Global Hourly KVLD 2024',
                              'url':'https://noaa-global-hourly-pds.s3.amazonaws.com/2024/72216693845.csv',
                              'best_track_provenance':'Possible NHC use is unknown; held out from this project’s structural development.',
                              'stations':[station.copy()]})
    series=pd.concat([series,*normalized],ignore_index=True)
    tracks=read_hurdat(args.tracks)
    with output_directory(args.out) as out:
        series.to_csv(out/'observed_time_series.csv',index=False)
        pd.concat(audits,ignore_index=True).to_csv(out/'reserved_qc_audit.csv',index=False)
        pd.concat(raw_events,ignore_index=True).to_csv(out/'reserved_raw_event_records.csv',index=False)
        summary=compare_candidates(series,plan,tracks,cfg,registered['candidates'],out,metadata)
        (out/'event_plan.json').write_text(json.dumps(plan,indent=2)+'\n')
        manifest={'registration':registered,'lock':lock,'config':cfg,'metadata':metadata,
                  'inputs_sha256':{str(p):sha256(p) for p in [args.registration,args.lock,args.annual,args.config,args.tracks,metadata_path,
                                      Path('data/validation/valdosta_event_plan.json'),Path('data/validation/valdosta_time_series.csv')]},
                  'code_sha256':{p.name:sha256(p) for p in Path(__file__).parent.glob('*.py')},
                  'versions':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__},
                  'outputs_sha256':output_hashes(out)}
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(summary.to_string(index=False))
    print(f'Reserved-event report: {args.out}/report.md')


if __name__=='__main__':
    main()

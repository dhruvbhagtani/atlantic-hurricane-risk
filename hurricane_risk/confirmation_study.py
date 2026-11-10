"""Evaluate the independently registered Laura confirmation without changing candidates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .artifacts import output_directory,output_hashes,sha256
from .global_hourly import normalize_global_hourly
from .model import read_hurdat,KNOT_TO_MS
from .structural_study import compare_candidates

REGISTRATION_SHA256='dc5fbda564c563be88dd4d033b19168b541b4eb45e31ae027495802f6436e932'


def entries_at(entries,date):
    at=pd.Timestamp(date)
    matches=[]
    for entry in entries:
        period=entry.get('date',{})
        start=pd.Timestamp(period.get('beginDate','1800-01-01'))
        end=period.get('endDate','Present')
        if start <= at and (end=='Present' or at <= pd.Timestamp(end)):
            matches.append(entry)
    return matches


def station_metadata(document,event):
    stations=document['stationCollection']['stations']
    identified=[]
    for station in stations:
        ids=entries_at(station['identifiers'],'2020-08-27')
        if (any(i['idType']=='WBAN' and i['id']=='03937' for i in ids)
                and any(i['idType']=='ICAO' and i['id']=='KLCH' for i in ids)):
            identified.append(station)
    if not identified:
        raise ValueError('Station identity is not documented during Laura')
    surface=[station for station in identified if any(
        p['platform']=='ASOS' for p in entries_at(station.get('platforms',[]),'2020-08-27'))]
    if len(surface)!=1:
        raise ValueError('Expected exactly one dated ASOS station history for KLCH')
    station=surface[0]
    positions=entries_at(station['location']['latLonPairs'],'2020-08-27')
    if not positions:
        raise ValueError('No dated station coordinates for Laura')
    position=max(positions,key=lambda e:e['date']['beginDate'])
    return {'station_id':'KLCH','ncei_id':event['ncei_id'],'homr_ncdc_id':station['ncdcStnId'],
            'history_selection':'Unique record with dated WBAN 03937, ICAO KLCH and ASOS platform during Laura.',
            'history_records_returned':len(stations),
            'lat':float(position['latitude_dec']),'lon':float(position['longitude_dec']),
            'height_m':10,'averaging_minutes':2,
            'height_duration_source':'https://www.weather.gov/lch/2020Laura-PSHLCH',
            'evidence':'The METAR section states 10-m anemometer height and two-minute wind averaging. KLCH is listed with incomplete sustained and gust peaks.',
            'wind_tower_coordinate_sensitivity':{'lat':30.12,'lon':-93.22,'source':'Rounded coordinates in NWS Laura METAR table, not an inferred sensor relocation.'},
            'exposure':'Quantitative directional roughness is not established.',
            'uptime':'NWS explicitly flags KLCH sustained and gust peaks incomplete. No claim of complete capture is made.'}


def validate_frozen_model(event,lock_path):
    if sha256(lock_path)!=event['frozen_model_lock_sha256']:
        raise ValueError('Frozen model lock changed')
    lock=json.loads(lock_path.read_text())
    for name,digest in lock['model_code_sha256'].items():
        if sha256(Path(__file__).parent/name)!=digest:
            raise ValueError(f'Model changed before confirmation: {name}')
    for name,digest in lock.get('support_inputs_sha256',{}).items():
        if sha256(name)!=digest:
            raise ValueError(f'Frozen study support input changed: {name}')
    cfg=json.loads(Path('examples/structural_config.json').read_text())
    if sha256(cfg['coastline_path'])!=lock['coastline_sha256']:
        raise ValueError('Frozen study coastline changed')
    original=json.loads(Path('data/validation/reserved_evaluation.json').read_text())
    if event['candidates']!=original['candidates']:
        raise ValueError('Confirmation candidates differ from the registered model comparison')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--registration',type=Path,default=Path('data/validation/laura_confirmation_registration.json'))
    p.add_argument('--annual',type=Path,default=Path('data/raw/global_hourly/2020/72240003937.csv'))
    p.add_argument('--homr',type=Path,default=Path('data/raw/metadata/homr_KLCH.json'))
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--tracks',type=Path,default=Path('data/hurdat2-1851-2024-040425.txt'))
    args=p.parse_args()
    if sha256(args.registration)!=REGISTRATION_SHA256:
        raise ValueError('Confirmation registration changed')
    event=json.loads(args.registration.read_text())
    frozen_path=Path('data/validation/structural_study_lock.json')
    validate_frozen_model(event,frozen_path)
    cfg=json.loads(Path('examples/structural_config.json').read_text())
    oldlock=json.loads(frozen_path.read_text())
    if sha256(cfg['coastline_path'])!=oldlock['coastline_sha256']:
        raise ValueError('Confirmation coastline differs from the frozen models')
    meta=station_metadata(json.loads(args.homr.read_text()),event)
    raw=pd.read_csv(args.annual,dtype=str,keep_default_na=False);raw['raw_file']=str(args.annual)
    series,qc,source=normalize_global_hourly(raw,event['storm_id'],event['station_id'],event['ncei_id'],
                                          event['window_start'],event['window_end'])
    station={'station_id':'KLCH','lat':meta['lat'],'lon':meta['lon'],'height_m':10,'averaging_minutes':2,
             'exposure':'unknown','cadence_minutes':60,'uptime_confirmed':False,
             'metadata_reference':meta['height_duration_source'],'uptime_reference':meta['height_duration_source']}
    plan={'quality_control_description':'Conservative NOAA Global Hourly wind QC; see raw QC audit.',
          'quality_control_reference':'https://www.ncei.noaa.gov/pub/data/noaa/isd-format-document.pdf',
          'events':[{'storm_id':event['storm_id'],'name':'Laura','split':'test',
                     'window_start':event['window_start'],'window_end':event['window_end'],
                     'product':'NOAA Global Hourly KLCH 2020','url':event['annual_url'],
                     'best_track_provenance':'Unknown NHC use; confirmation withheld from this project’s model development.',
                     'stations':[station]}]}
    tracks=read_hurdat(args.tracks)
    input_hashes={str(p):sha256(p) for p in [args.registration,args.annual,args.homr,args.tracks]}
    code_hashes={p.name:sha256(p) for p in Path(__file__).parent.glob('*.py')}
    with output_directory(args.out) as out:
        summary=compare_candidates(series,plan,tracks,cfg,event['candidates'],out,meta)
        series.to_csv(out/'observed_time_series.csv',index=False)
        qc.to_csv(out/'qc_audit.csv',index=False)
        source.to_csv(out/'raw_event_records.csv',index=False)
        (out/'station_metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
        (out/'homr_KLCH.json').write_text(args.homr.read_text())
        pairs=pd.read_csv(out/'time_matched_pairs.csv')
        rows=[]
        for variant,group in pairs[pairs.sample_eligible].groupby('variant',sort=False):
            high=group[group.sustained_ms>=64*KNOT_TO_MS]
            rows.append({'variant':variant,'samples':len(group),'hurricane_force_samples':len(high),
                         'observed_sampled_peak_ms':group.sustained_ms.max(),
                         'high_wind_bias_ms':float(high.residual_ms.mean()) if len(high) else np.nan,
                         'high_wind_rmse_ms':float(np.sqrt((high.residual_ms**2).mean())) if len(high) else np.nan})
        pd.DataFrame(rows).to_csv(out/'high_wind_scores.csv',index=False)
        text=['# Laura high-wind confirmation','',
              'Laura at Lake Charles was registered after Debby/Milton evaluation as an additional high-wind and geographic confirmation.',
              'The reported NWS event intensity was known when selecting this case; station-series values and model residuals were not.',
              'All candidate parameters, model source hashes and coastline remain unchanged from the frozen comparison.',
              'NWS documents 10-m, two-minute METAR winds and explicitly flags the KLCH event peak incomplete.',
              'Scores use good-QC samples at their actual report times. They do not certify a continuously observed peak or full spatial core.',
              'Site roughness remains unknown; exposure and coordinate alternatives are retained without selection.','',
              '| Candidate | Samples | Bias (m/s) | RMSE (m/s) |','|---|---:|---:|---:|']
        perf=pd.read_csv(out/'performance.csv')
        for r in perf.itertuples():text.append(f'| {r.variant} | {r.n} | {r.bias_ms:.2f} | {r.rmse_ms:.2f} |')
        text += ['',f"Samples meeting the 64-kt threshold ({64*KNOT_TO_MS:.4f} m/s): {rows[0]['hurricane_force_samples']}.",
                 '', '| Candidate | High-wind samples | High-wind bias (m/s) | High-wind RMSE (m/s) |',
                 '|---|---:|---:|---:|']
        for r in rows:
            text.append(f"| {r['variant']} | {r['hurricane_force_samples']} | {r['high_wind_bias_ms']:.2f} | {r['high_wind_rmse_ms']:.2f} |")
        coverage=pd.read_csv(out/'coverage.csv').iloc[0]
        text += ['', 'A small signed bias can conceal cancellation between overprediction and underprediction; consult RMSE and the sample residuals.',
                 'These samples are not independent storm replicates.',
                 f"The good sampled peak is {rows[0]['observed_sampled_peak_ms']:.2f} m/s. It remains a lower bound on the complete event peak.",
                 f"Good reports occupy {coverage.good_cadence_bins} of {coverage.expected_reports} planned cadence bins ({coverage.coverage:.1%}).",
                 f"The maximum gap, including window boundaries, is {coverage.max_gap_minutes:.0f} minutes; uptime is unconfirmed.",
                 f"The surface station history is NCDC {meta['homr_ncdc_id']}, selected by dated ASOS and station identifiers from {meta['history_records_returned']} returned records.",
                 'All results, including failures or underprediction, are reported; no candidate is promoted from these scores.',
                 'See coverage.csv for outages, qc_audit.csv for exclusions, and the source hashes in manifest.json.','']
        (out/'report.md').write_text('\n'.join(text))
        manifest={'registration':event,'frozen_model_lock_sha256':sha256(frozen_path),'config':cfg,
                  'inputs_sha256':input_hashes,
                  'code_sha256':code_hashes,
                  'outputs_sha256':output_hashes(out)}
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(summary.to_string(index=False));print(pd.DataFrame(rows).to_string(index=False))


if __name__=='__main__':main()

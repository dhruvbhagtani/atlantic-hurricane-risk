"""Check the registered Laura case against a source-attributed NWS high-wind report."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .artifacts import output_directory,output_hashes,sha256
from .confirmation_study import validate_frozen_model,REGISTRATION_SHA256
from .model import read_hurdat,KNOT_TO_MS
from .time_series_validation import modeled_at_times


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--tracks',type=Path,default=Path('data/hurdat2-1851-2024-040425.txt'))
    args=p.parse_args()
    registration=Path('data/validation/laura_confirmation_registration.json')
    if sha256(registration)!=REGISTRATION_SHA256:raise ValueError('Laura registration changed')
    event=json.loads(registration.read_text())
    validate_frozen_model(event,Path('data/validation/structural_study_lock.json'))
    cfg=json.loads(Path('examples/structural_config.json').read_text())
    observed_path=Path('data/validation/laura_reported_point.csv')
    observed=pd.read_csv(observed_path)
    tracks=read_hurdat(args.tracks)
    rows=[]
    for item in observed.itertuples():
        tr=tracks[tracks.storm_id.eq(item.storm_id)]
        time=pd.to_datetime([item.time_utc],utc=True)
        for variant in event['candidates']:
            run_cfg={**cfg,**variant['overrides']}
            station={'lat':item.lat,'lon':item.lon}
            predicted=float(modeled_at_times(tr,station,time,run_cfg)[0])
            grid=[]
            half=item.coordinate_precision_deg/2
            for dy in [-half,0,half]:
                for dx in [-half,0,half]:
                    grid.append(float(modeled_at_times(tr,{'lat':item.lat+dy,'lon':item.lon+dx},time,run_cfg)[0]))
            rows.append({'variant':variant['name'],'storm_id':item.storm_id,'station_id':item.station_id,
                         'time_utc':item.time_utc,'reported_ms':item.sustained_kt*KNOT_TO_MS,
                         'modeled_ms':predicted,'error_ms':predicted-item.sustained_kt*KNOT_TO_MS,
                         'coordinate_grid_min_ms':min(grid),'coordinate_grid_max_ms':max(grid),
                         'incomplete_event_peak':item.incomplete_event_peak})
    result=pd.DataFrame(rows)
    with output_directory(args.out) as out:
        result.to_csv(out/'reported_point_comparison.csv',index=False)
        observed.to_csv(out/'source_observation.csv',index=False)
        text=['# Laura reported high-wind point check','',
              'The NWS corrected Laura METAR report documents KLCH sustained wind of 85 kt at 06:54 UTC on 27 August 2020.',
              'Its header specifies 10-m height and two-minute averaging. The event peak is explicitly incomplete.',
              'The fixed candidates are compared at that report time, not against a presumed complete event maximum.',
              'The reported value was known when the Laura case was selected; no Laura residuals or station-series values',
              'were used to change candidates. This is a source-reviewed report check, separate from provider-QC time-series validation.','',
              '| Candidate | Reported (m/s) | Modeled (m/s) | Signed error (m/s) | Coordinate-grid range (m/s) |',
              '|---|---:|---:|---:|---:|']
        for r in result.itertuples():
            text.append(f'| {r.variant} | {r.reported_ms:.2f} | {r.modeled_ms:.2f} | {r.error_ms:+.2f} | {r.coordinate_grid_min_ms:.2f}–{r.coordinate_grid_max_ms:.2f} |')
        text += ['', 'The nine-point coordinate grid spans the published coordinate rounding (±0.005 degrees). It is a location',
                 'sensitivity, not a predictive interval and not an allowance for unobserved storm-center errors.',
                 'One reported high-wind point does not validate a spatial hurricane core, complete event peak or population skill.',
                 'The one-minute model and two-minute observation retain the nominal-duration comparison; no conversion is fitted.',
                 'Unknown site roughness and station/track uncertainty remain. The requested full NOAA Laura series is still a separate pending input.',
                 'No candidate is selected or promoted from this check.','',
                 f'[NWS Laura post-storm report]({observed.source_url.iloc[0]}).','']
        (out/'report.md').write_text('\n'.join(text))
        manifest={'registration':event,'config':cfg,
                  'inputs_sha256':{str(p):sha256(p) for p in [registration,observed_path,args.tracks]},
                  'frozen_model_lock_sha256':sha256('data/validation/structural_study_lock.json'),
                  'outputs_sha256':output_hashes(out)}
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(result.to_string(index=False))


if __name__=='__main__':main()

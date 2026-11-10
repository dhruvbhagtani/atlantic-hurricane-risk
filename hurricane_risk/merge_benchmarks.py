"""Combine small structural benchmark batches, requiring identical baseline results."""
import argparse
import json
from pathlib import Path
import shutil
import os
os.environ.setdefault("MPLCONFIGDIR", "/tmp/hurricane-risk-matplotlib")

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .artifacts import output_directory,output_hashes,sha256


TABLES=['summary.csv','station_skill.csv','station_pairs.csv','grouped_errors.csv',
        'annual_losses.csv','event_losses.csv','convergence.csv']


def merge_batches(batches,out):
    manifests=[json.loads((p/'manifest.json').read_text()) for p in batches]
    for other in manifests[1:]:
        if other['config']!=manifests[0]['config'] or other['coastline_sha256']!=manifests[0]['coastline_sha256']:
            raise ValueError('Batch configuration or coastline mismatch')
        for name in ['model.py','geography.py','time_series_validation.py']:
            if other['code_sha256'][name]!=manifests[0]['code_sha256'][name]:
                raise ValueError('Core wind model differs between batches')
    common=set.intersection(*(set(m['inputs_sha256']) for m in manifests))
    if len(common)<4:
        raise ValueError('Expected common track, config, observation and source inputs')
    for name in common:
        if len({m['inputs_sha256'][name] for m in manifests})!=1:
            raise ValueError(f'Batch input mismatch: {name}')
    if len({sha256(p/'portfolio.csv') for p in batches})!=1:
        raise ValueError('Batch exposure mismatch')
    for filename in TABLES:
        frames=[pd.read_csv(p/filename,keep_default_na=False) for p in batches]
        baseline=frames[0][frames[0].variant.eq('baseline')].reset_index(drop=True)
        for frame in frames[1:]:
            pd.testing.assert_frame_equal(baseline,frame[frame.variant.eq('baseline')].reset_index(drop=True))
        pd.concat(frames,ignore_index=True).drop_duplicates().to_csv(out/filename,index=False)
    shutil.copyfile(batches[0]/'portfolio.csv',out/'portfolio.csv')
    summary=pd.read_csv(out/'summary.csv')
    text=['# Structural wind and insured-loss comparison','',
          'These batches use identical original synthetic exposure and the same one-minute wind resolution.',
          'Every repeated baseline table was required to match exactly before combining results.',
          'Baseline convergence against 15-second sampling is documented separately. No candidate is fitted or selected here.','',
          '| Candidate | Peak-station RMSE (m/s) | Bias (m/s) | Insured AAL | AAL change |',
          '|---|---:|---:|---:|---:|']
    for r in summary.itertuples():
        text.append(f'| {r.variant} | {r.rmse_ms:.2f} | {r.bias_ms:.2f} | ${r.aal_usd:,.0f} | {r.aal_change_vs_baseline_pct:+.2f}% |')
    text += ['', 'Peak scores use the original eligible primary observations. The separate frozen report-time study evaluates',
             'new reserved events. Inland attenuation and translation asymmetry remain declared model assumptions.',
             'The original exposure includes offshore synthetic coordinates; the land-only exposure and its numerical check',
             'are documented separately so exposure relocation is not confounded with a hazard-model change.',
             'No insured-claims calibration, physical climate attribution or complete high-wind footprint validation is asserted.','',
             '![Structural comparison](comparison.png)','']
    (out/'report.md').write_text('\n'.join(text))
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    x=np.arange(len(summary))
    axes[0].bar(x,summary.rmse_ms,color='steelblue');axes[0].set(ylabel='Peak-station RMSE (m/s)')
    axes[1].bar(x,summary.aal_usd/1e6,color='darkorange');axes[1].set(ylabel='Insured AAL (USD millions)')
    for ax in axes:
        ax.set_xticks(x,summary.variant,rotation=30,ha='right',fontsize=7)
    fig.tight_layout();fig.savefig(out/'comparison.png',dpi=170);plt.close(fig)
    (out/'batch_manifests.json').write_text(json.dumps(manifests,indent=2)+'\n')
    manifest={'source_batches':{str(p):sha256(p/'manifest.json') for p in batches},
              'rule':'Repeated baseline tables and portfolio must match exactly; duplicate rows removed only after verification.',
              'outputs_sha256':output_hashes(out)}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batches',type=Path,nargs='+',required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    with output_directory(args.out) as out:
        result=merge_batches(args.batches,out)
    print(result.to_string(index=False))


if __name__=='__main__':main()

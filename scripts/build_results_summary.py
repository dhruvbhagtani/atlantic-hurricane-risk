"""Build a compact review report from the completed, archived studies."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('MPLCONFIGDIR','/tmp/hurricane-risk-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from hurricane_risk.artifacts import output_directory,output_hashes,sha256


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    paths={
        'original_resolution':Path('reports/subminute_convergence/summary.csv'),
        'land_resolution':Path('reports/land_only_resolution/summary.csv'),
        'structural':Path('reports/structural_models/summary.csv'),
        'reserved':Path('reports/reserved_structural_study/storm_balanced_summary.csv'),
        'current':Path('reports/current_default_historical/summary.csv'),
        'locations':Path('reports/land_only_exposure/location_audit.csv')}
    point_path=Path('reports/laura_reported_point_check/reported_point_comparison.csv')
    if point_path.exists():paths['high_wind_point']=point_path
    frames={key:pd.read_csv(path) for key,path in paths.items()}
    test=frames['reserved'][frames['reserved'].split.eq('test')]
    current=frames['current'].set_index('scenario')
    with output_directory(args.out) as out:
        fig,axes=plt.subplots(1,4 if 'high_wind_point' in frames else 3,figsize=(19 if 'high_wind_point' in frames else 15,5))
        for key,label in [('original_resolution','Original exposure'),('land_resolution','Land-only exposure')]:
            frame=frames[key]
            axes[0].plot(frame.interpolation_minutes,frame.aal_usd/1e3,marker='o',label=label)
        axes[0].set(xlabel='Timestep (minutes)',ylabel='Insured AAL (USD thousands)',title='Numerical resolution')
        axes[0].legend(fontsize=8)
        x=np.arange(len(test));axes[1].bar(x,test.storm_mean_rmse_ms,color='steelblue')
        axes[1].set(ylabel='Storm-mean RMSE (m/s)',title='Reserved Debby/Milton samples')
        axes[1].set_xticks(x,test.variant,rotation=30,ha='right',fontsize=7)
        structure=frames['structural'];x=np.arange(len(structure))
        axes[2].bar(x,structure.aal_usd/1e3,color='darkorange')
        axes[2].set(ylabel='Insured AAL (USD thousands)',title='Structural sensitivity: fixed original exposure')
        axes[2].set_xticks(x,structure.variant,rotation=30,ha='right',fontsize=7)
        if 'high_wind_point' in frames:
            point=frames['high_wind_point'];x=np.arange(len(point))
            axes[3].bar(x,point.modeled_ms,color='steelblue')
            axes[3].axhline(point.reported_ms.iloc[0],color='black',ls='--',label='NWS reported wind')
            axes[3].set(ylabel='Sustained wind (m/s)',title='Laura: one reported high-wind point')
            axes[3].set_xticks(x,point.variant,rotation=30,ha='right',fontsize=7);axes[3].legend(fontsize=7)
        fig.tight_layout();fig.savefig(out/'overview.png',dpi=170);plt.close(fig)
        text=['# Project completion and evidence','',
              'The five requested engineering areas now have implemented workflows and completed local evaluations.',
              'Scientific scope is explicit: no claim of complete high-wind footprints or insured-loss calibration is made.','',
              '| Area | Delivered evidence |','|---|---|',
              '| Observational benchmark | Downloaded QC time series, dated station history, documented height/duration, registered Debby/Milton tests, coverage and censoring audits. |',
              '| Wind diagnosis and candidates | Inland-distance bins and coastline uncertainty; size, translation asymmetry, local inland attenuation and combined candidates; all results retained. |',
              '| Numerical convergence | One-minute sampling meets 1 m/s and 1% criteria against 15 seconds for both original and land-only exposures. |',
              '| Exposure/vulnerability | Validated custom inputs; land-only seeded exposure with financial terms preserved and all relocations recorded. |',
              '| Workflow reliability | Protected atomic outputs, input/output/code hashes, dependency pins, offline integration tests and GitHub Actions. |','',
              'The original five storms remain development diagnostics. The separately reserved Debby and Milton windows',
              'supply 260 good-QC samples supported by best-track times at one station. Model parameters were frozen',
              'before those station-series winds or errors were examined. Independence from NHC best-track inputs is not established.','',
              '| Candidate | Reserved storm-mean bias (m/s) | Reserved storm-mean RMSE (m/s) |',
              '|---|---:|---:|']
        for r in test.itertuples():text.append(f'| {r.variant} | {r.storm_mean_bias_ms:.2f} | {r.storm_mean_rmse_ms:.2f} |')
        text += ['', 'These conditional, report-time scores do not select a winning model. All original structural parameters',
                 'remain fixed, and the optional candidates are disabled in the production baseline. Quantitative directional',
                 'site roughness and complete uptime are unresolved; censored sampled peaks are never promoted to complete peaks.','',
                 f"The current default historical AAL is **${current.loc['historical','aal_usd']:,.0f}**. It uses one-minute sampling",
                 'and synthetic locations at least 2 km inside the generalized land mask. Values, construction and policy',
                 'terms are preserved. Of the original 300 points, 85 mapped offshore; the 2-km buffer relocates 169 points',
                 'including near-shore points, with a maximum displacement of 10.67 km. These remain synthetic locations, not verified parcels.','',
                 'For the current exposure, one-minute AAL differs from the 15-second reference by 0.68%; maximum event/property',
                 'wind difference is 0.73 m/s. The finest tested timestep is still a numerical reference, not proof about unresolved storm evolution.',
                 'The legacy 30-minute configuration reproduces the prior historical tables exactly.','',
                 '![Resolution, reserved samples and structural sensitivity](overview.png)','',
                 'Linked reports: [current default](../current_default_historical/report.md),',
                 '[structural loss comparison](../structural_models/report.md),',
                 '[frozen reserved-event study](../reserved_structural_study/report.md),',
                 '[original exposure resolution](../subminute_convergence/report.md),',
                 '[land-only resolution](../land_only_resolution/report.md).','',
                 'The additional Lake Charles/Laura high-wind confirmation is registered, with an importer and unchanged-model checks.',
                 'Its station-year download is a separate pending input; it is not represented as completed validation here.','']
        if 'high_wind_point' in frames:
            text += ['The separate [NWS Laura reported-point check](../laura_reported_point_check/report.md) records 43.73 m/s',
                     'at the reported time, compared with 26.99 m/s for the baseline and 18.39 m/s for inland attenuation.',
                     'The latter improves the lower-wind reserved score but worsens this high-wind comparison. It is kept optional.',
                     'The NWS event peak is incomplete; this single source-reviewed point is not a full provider-QC time series or spatial validation.','']
        (out/'report.md').write_text('\n'.join(text))
        manifest={'inputs_sha256':{str(path):sha256(path) for path in paths.values()},
                  'outputs_sha256':output_hashes(out)}
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(args.out/'report.md')


if __name__=='__main__':main()

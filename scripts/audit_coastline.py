"""Reproduce land classification and coastal-distance sensitivity for study sites."""
import argparse
import json
from pathlib import Path
import sys
import os
os.environ.setdefault("MPLCONFIGDIR", "/tmp/hurricane-risk-matplotlib")

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from shapely import get_parts
from shapely.geometry import box

from hurricane_risk.artifacts import output_directory,output_hashes,sha256
from hurricane_risk.geography import coast_distances,load_coastline
from hurricane_risk.model import synthetic_portfolio


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    points=synthetic_portfolio(300,7319)[['property_id','lat','lon']].rename(columns={'property_id':'site_id'})
    obs=pd.read_csv('data/validation/expanded_station_peaks.csv')
    stations=obs[['station_id','lat','lon']].drop_duplicates().rename(columns={'station_id':'site_id'})
    points=pd.concat([points.assign(kind='synthetic_property'),stations.assign(kind='station')],ignore_index=True)
    for scale in ['10m','50m']:
        path=f'data/geography/natural_earth_{scale}_atlantic.geojson.gz'
        distance,land=coast_distances(points.lat,points.lon,path)
        points[f'distance_{scale}_km']=distance;points[f'land_{scale}']=land
    points['near_coast_uncertain']=points.distance_10m_km.abs().lt(5)
    points['scale_difference_km']=points.distance_10m_km-points.distance_50m_km
    with output_directory(args.out) as out:
        points.to_csv(out/'site_audit.csv',index=False)
        summary={'sites':len(points),'classification_disagreements':int(points.land_10m.ne(points.land_50m).sum()),
                 'synthetic_properties_offshore':int((points.kind.eq('synthetic_property') & ~points.land_10m).sum()),
                 'sites_within_5km_shore':int(points.near_coast_uncertain.sum()),
                 'maximum_signed_distance_difference_km':float(points.scale_difference_km.abs().max()),
                 'method':'Nearest shoreline point in a regional equirectangular projection; final spherical distance. Clipping edges excluded.',
                 'limits':'Generalized shoreline, not parcel geometry. Near-coast sites carry a 5-km diagnostic uncertainty flag. Offshore synthetic points are retained and not snapped.'}
        (out/'audit.json').write_text(json.dumps(summary,indent=2)+'\n')
        fig,ax=plt.subplots(figsize=(8,7))
        land,*_=load_coastline('data/geography/natural_earth_10m_atlantic.geojson.gz')
        coast=land.boundary.intersection(box(-89,23.5,-78.5,32.5))
        for line in get_parts(coast):
            x,y=line.xy;ax.plot(x,y,color='steelblue',lw=.4)
        properties=points[points.kind.eq('synthetic_property')]
        for inside,color,label in [(True,'forestgreen','Mapped on land'),(False,'crimson','Mapped offshore')]:
            group=properties[properties.land_10m.eq(inside)]
            ax.scatter(group.lon,group.lat,color=color,s=15,alpha=.7,label=label)
        ax.set(xlim=(-88.5,-79),ylim=(24,32),xlabel='Longitude',ylabel='Latitude',
               title='Original synthetic exposure: coastline audit')
        ax.set_aspect(1/.8660254);ax.legend();fig.tight_layout();fig.savefig(out/'coast_audit.png',dpi=160);plt.close(fig)
        manifest={'inputs_sha256':{name:sha256(name) for name in [
            'data/geography/natural_earth_10m_atlantic.geojson.gz','data/geography/natural_earth_50m_atlantic.geojson.gz',
            'data/validation/expanded_station_peaks.csv']},'outputs_sha256':output_hashes(out)}
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()

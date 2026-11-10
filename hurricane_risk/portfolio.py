"""Generate synthetic land-only exposure while retaining values, IDs and policy terms."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .artifacts import output_directory, output_hashes, sha256
from .geography import coast_distances
from .model import synthetic_portfolio, distance_km


def land_only_portfolio(properties, seed, coastline_path, min_inland_km=2., half_width_deg=.075):
    if properties < 1 or not np.isfinite(min_inland_km) or min_inland_km < 0 or not np.isfinite(half_width_deg) or half_width_deg <= 0:
        raise ValueError('Need positive property count/radius and nonnegative inland buffer')
    original = synthetic_portfolio(properties, seed)
    result = original.copy()
    rng = np.random.default_rng(seed+20)
    before, _ = coast_distances(original.lat, original.lon, coastline_path)
    after = before.copy()
    attempts = np.zeros(properties,dtype=int)
    for _ in range(256):
        pending = np.flatnonzero(after < min_inland_km)
        if not len(pending):
            break
        # Proposal region is tied to the original location; it does not drift.
        lat = original.lat.to_numpy()[pending]+rng.uniform(-half_width_deg,half_width_deg,len(pending))
        lon = original.lon.to_numpy()[pending]+rng.uniform(-half_width_deg,half_width_deg,len(pending))
        distances, on_land = coast_distances(lat,lon,coastline_path)
        accepted = on_land & (distances >= min_inland_km)
        take = pending[accepted]
        result.loc[take,'lat'] = lat[accepted];result.loc[take,'lon'] = lon[accepted]
        after[take] = distances[accepted]
        attempts[pending] += 1
    if (after < min_inland_km).any():
        raise ValueError('Could not locate all properties inside the declared land buffer')
    audit=pd.DataFrame({'property_id':original.property_id,'original_lat':original.lat,'original_lon':original.lon,
                        'lat':result.lat,'lon':result.lon,'original_signed_coast_km':before,
                        'signed_coast_km':after,'proposal_attempts':attempts,
                        'displacement_km':distance_km(original.lat,original.lon,result.lat,result.lon)})
    return result,audit


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--properties',type=int,default=300)
    p.add_argument('--seed',type=int,default=7319)
    p.add_argument('--coastline',type=Path,default=Path('data/geography/natural_earth_10m_atlantic.geojson.gz'))
    p.add_argument('--min-inland-km',type=float,default=2.)
    p.add_argument('--half-width-deg',type=float,default=.075)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    portfolio,audit=land_only_portfolio(args.properties,args.seed,args.coastline,args.min_inland_km,args.half_width_deg)
    with output_directory(args.out) as out:
        portfolio.to_csv(out/'portfolio.csv',index=False)
        audit.to_csv(out/'location_audit.csv',index=False)
        manifest={'kind':'SYNTHETIC LAND-ONLY EXPOSURE; NOT VERIFIED PARCELS',
                  'properties':args.properties,'seed':args.seed,'location_seed':args.seed+20,
                  'min_inland_km':args.min_inland_km,'proposal_half_width_deg':args.half_width_deg,
                  'coastline_sha256':sha256(args.coastline),'relocated_properties':int(audit.displacement_km.gt(0).sum()),
                  'maximum_displacement_km':float(audit.displacement_km.max()),
                  'unchanged_fields':'IDs, city labels, construction, values, deductibles and limits',
                  'limits':'On-land classification uses generalized Natural Earth geometry, not a verified address or building inventory.',
                  'code_sha256':{p.name:sha256(p) for p in Path(__file__).parent.glob('*.py')},
                  'outputs_sha256':output_hashes(out)}
        (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f"Generated {len(portfolio)} synthetic land-only properties; relocated {manifest['relocated_properties']}")


if __name__=='__main__':main()

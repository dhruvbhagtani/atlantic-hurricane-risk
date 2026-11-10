"""Track-relative station diagnostics; geometric quantities, without a land mask."""
import numpy as np
import pandas as pd

from .model import distance_km, interpolate_track
from .validation import scores


def station_geometry(pairs, tracks, sources, cfg):
    result = pairs.copy()
    rows = []
    for row in result.itertuples():
        source = sources['sources'][row.source_id]
        track = tracks[(tracks.storm_id == row.storm_id) &
                       tracks.time.between(source['window_start'], source['window_end'])]
        lat, lon, wind, rmw = interpolate_track(track, cfg['interpolation_minutes'], cfg['rmw_km'])
        r = distance_km(lat, lon, row.lat, row.lon)
        closest = int(np.argmin(r))
        a, b = max(closest-1, 0), min(closest+1, len(lat)-1)
        # Local east/north vectors; unwrap station offset for dateline crossings.
        dx = (lon[b]-lon[a]) * np.cos(np.deg2rad(lat[closest]))
        dy = lat[b]-lat[a]
        px = ((row.lon-lon[closest]+180) % 360-180) * np.cos(np.deg2rad(lat[closest]))
        py = row.lat-lat[closest]
        cross = dx*py-dy*px
        side = 'stationary_or_on_track' if abs(cross) < 1e-10 else ('left' if cross > 0 else 'right')
        rows.append({'closest_distance_km': r[closest], 'closest_rmw_km': rmw[closest],
                     'distance_over_rmw': r[closest]/rmw[closest],
                     'closest_vmax_ms': wind[closest], 'side_of_track': side,
                     'rmw_missing_fraction': float(track.rmw_km.isna().mean())})
    return pd.concat([result.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def grouped_errors(pairs):
    primary = pairs[pairs.primary].copy()
    primary['distance_bin_km'] = pd.cut(primary.closest_distance_km, [0, 35, 100, 200, np.inf],
                                       include_lowest=True).astype(str)
    primary['intensity_bin_ms'] = pd.cut(primary.closest_vmax_ms, [0, 33, 50, 70, np.inf],
                                        include_lowest=True).astype(str)
    primary['rmw_availability'] = np.where(primary.rmw_missing_fraction > 0, 'some_missing', 'all_observed')
    rows = []
    for dimension in ['split', 'storm_id', 'side_of_track', 'distance_bin_km', 'intensity_bin_ms', 'rmw_availability']:
        for label, group in primary.groupby(dimension, observed=True):
            rows.append({'dimension': dimension, 'group': str(label),
                         'storms': group.storm_id.nunique(), **scores(group.observed_ms, group.modeled_ms)})
    return pd.DataFrame(rows)

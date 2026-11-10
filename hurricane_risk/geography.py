"""Provenance-backed land classification and approximate nearest-coast distances."""
from functools import lru_cache
import json
import gzip
from pathlib import Path

import numpy as np
from shapely import contains_xy
from shapely.geometry import Point, shape
from shapely.ops import nearest_points, transform


@lru_cache(maxsize=8)
def load_coastline(path):
    data = Path(path).read_bytes()
    document = json.loads(gzip.decompress(data) if str(path).endswith('.gz') else data)
    roles = {f['properties']['role']: shape(f['geometry']) for f in document['features']}
    if set(roles) != {'land', 'coastline'} or not all(g.is_valid and not g.is_empty for g in roles.values()):
        raise ValueError('Need valid nonempty land and coastline geometries')
    meta = document['provenance']
    if not meta.get('source_shp_sha256') or not meta.get('source_url'):
        raise ValueError('Coastline provenance is required')
    # Regional equirectangular projection only locates the nearest segment; the
    # final point-to-coast distance uses the spherical great-circle formula.
    cos30 = np.cos(np.deg2rad(30))
    factor = 6371.0088*np.pi/180
    def project(x, y, z=None):
        return ((np.asarray(x)+80)*factor*cos30, (np.asarray(y)-30)*factor)
    projected = transform(project, roles['coastline'])
    return roles['land'], projected, meta, factor, cos30


@lru_cache(maxsize=128)
def _distances(path, latitudes, longitudes):
    from .model import distance_km
    land, coast, meta, factor, cos30 = load_coastline(path)
    lat, lon = np.asarray(latitudes), np.asarray(longitudes)
    west, south, east, north = meta['evaluation_bounds']
    if not (np.isfinite(lat).all() and np.isfinite(lon).all() and
            ((lon >= west) & (lon <= east) & (lat >= south) & (lat <= north)).all()):
        raise ValueError('Coastline evaluation outside its audited regional bounds')
    on_land = contains_xy(land, lon, lat)
    distances = []
    for y, x, inside in zip(lat, lon, on_land):
        closest = nearest_points(Point((x+80)*factor*cos30, (y-30)*factor), coast)[1]
        coast_lon, coast_lat = closest.x/(factor*cos30)-80, closest.y/factor+30
        distance = float(distance_km(y, x, coast_lat, coast_lon))
        distances.append(distance if inside else -distance)
    return np.asarray(distances), on_land


def coast_distances(latitudes, longitudes, path):
    distances, land = _distances(str(Path(path).resolve()), tuple(np.asarray(latitudes, dtype=float)),
                                 tuple(np.asarray(longitudes, dtype=float)))
    return distances.copy(), land.copy()

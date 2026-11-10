"""Build a regional coastline artifact from Natural Earth Polygon shapefiles."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
from shapely.geometry import Polygon, MultiPolygon, box, mapping
from shapely.ops import unary_union
from shapely.validation import make_valid


def read_polygons(path):
    data = Path(path).read_bytes()
    if struct.unpack_from('>i', data)[0] != 9994 or struct.unpack_from('<i', data, 32)[0] != 5:
        raise ValueError('Expected an ESRI Polygon shapefile')
    if struct.unpack_from('>i', data, 24)[0]*2 != len(data):
        raise ValueError('Shapefile length mismatch')
    offset, polygons, repairs = 100, [], 0
    while offset < len(data):
        length = struct.unpack_from('>i', data, offset+4)[0]*2
        body = data[offset+8:offset+8+length]
        shape_type = struct.unpack_from('<i', body)[0]
        if shape_type == 0:
            offset += length+8
            continue
        if shape_type != 5:
            raise ValueError('Unexpected shape type')
        parts, points = struct.unpack_from('<2i', body, 36)
        starts = np.frombuffer(body, dtype='<i4', count=parts, offset=44)
        coordinates = np.frombuffer(body, dtype='<f8', count=points*2, offset=44+4*parts).reshape(-1, 2)
        rings = [coordinates[a:b] for a,b in zip(starts, [*starts[1:], points])]
        outers, holes = [], []
        for ring in rings:
            area = np.sum(ring[:-1,0]*ring[1:,1]-ring[1:,0]*ring[:-1,1])*.5
            (outers if area < 0 else holes).append(ring)
        if not outers:
            raise ValueError('Polygon record has no clockwise outer ring')
        associated = [[] for _ in outers]
        for hole in holes:
            point = Polygon(hole).representative_point()
            containing = [(Polygon(outer).area, i) for i,outer in enumerate(outers) if Polygon(outer).covers(point)]
            if not containing:
                raise ValueError('Unassigned interior ring')
            associated[min(containing)[1]].append(hole)
        for outer, inner in zip(outers, associated):
            poly = Polygon(outer, inner)
            if not poly.is_valid:
                repairs += 1
                poly = make_valid(poly)
            polygons.append(poly)
        offset += length+8
    return polygons, repairs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shapefile', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--scale', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--source-url', default='https://www.naturalearthdata.com/downloads/50m-physical-vectors/50m-land/')
    args=parser.parse_args()
    if args.out.exists():
        raise ValueError('Output exists')
    polygons, repairs=read_polygons(args.shapefile)
    land=unary_union(polygons)
    region=box(-110, -5, -40, 60)
    # Clip the existing coastline, never use new clipping edges as shoreline.
    coast=land.boundary.intersection(region)
    document={'type':'FeatureCollection','features':[
        {'type':'Feature','properties':{'role':'land'},'geometry':mapping(land.intersection(region))},
        {'type':'Feature','properties':{'role':'coastline'},'geometry':mapping(coast)}],
        'provenance':{'dataset':'Natural Earth land','version':args.version,'scale':args.scale,
          'source_url':args.source_url,
          'license_url':'https://www.naturalearthdata.com/about/terms-of-use/',
          'source_shp_sha256':hashlib.sha256(args.shapefile.read_bytes()).hexdigest(),
          'projection':args.shapefile.with_suffix('.prj').read_text(),
          'polygon_records':len(polygons),'invalid_geometries_repaired':repairs,
          'clip_bounds':list(region.bounds),'evaluation_bounds':[-100,0,-55,50],
          'limits':'Generalized shoreline including major islands. Not parcel-scale or a surveyed coastline; small islands and estuaries may be omitted.'}}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(document,separators=(',',':'))+'\n')
    print(args.out, args.out.stat().st_size, 'bytes', len(polygons),'polygons',repairs,'repairs')


if __name__=='__main__':
    main()

#!/usr/bin/env python3
"""Fetch OSM features from Overpass and convert to simple GeoJSON (ways with geometry).

Usage: python3 scripts/fetch_overpass_geojson.py <type> <south> <west> <north> <east> <out.geojson>
type: forest|water
"""
import sys
import json
from urllib import request, parse

if len(sys.argv) != 7:
    print(__doc__)
    sys.exit(2)

typ, south, west, north, east, outp = sys.argv[1:7]
bbox = f"{south},{west},{north},{east}"

if typ == 'forest':
    queries = [
        f"way[\"landuse\"=\"forest\"]({bbox});",
        f"way[\"landcover\"=\"forest\"]({bbox});",
        f"way[\"natural\"=\"wood\"]({bbox});",
        f"relation[\"landuse\"=\"forest\"]({bbox});",
        f"relation[\"landcover\"=\"forest\"]({bbox});",
    ]
elif typ == 'water':
    queries = [
        f"way[\"natural\"=\"water\"]({bbox});",
        f"way[\"landuse\"=\"reservoir\"]({bbox});",
        f"relation[\"natural\"=\"water\"]({bbox});",
    ]
else:
    print('Unknown type', typ)
    sys.exit(2)

ql = '[out:json][timeout:180];(' + '\n'.join(queries) + ');out geom;'

payload = parse.urlencode({'data': ql}).encode('utf-8')
req = request.Request('https://overpass-api.de/api/interpreter', data=payload, headers={'Content-Type':'application/x-www-form-urlencoded'})
print('Fetching Overpass for', typ, 'bbox', bbox, file=sys.stderr)
resp = request.urlopen(req)
osm = json.load(resp)

features = []
for el in osm.get('elements', []):
    if el.get('type') == 'way' and 'geometry' in el:
        coords = [[pt['lon'], pt['lat']] for pt in el['geometry']]
        geom = None
        if len(coords) >= 4 and coords[0] == coords[-1]:
            geom = { 'type': 'Polygon', 'coordinates': [coords] }
        else:
            geom = { 'type': 'LineString', 'coordinates': coords }
        feat = { 'type': 'Feature', 'id': el.get('id'), 'properties': el.get('tags', {}), 'geometry': geom }
        features.append(feat)
    elif el.get('type') == 'relation':
        # relations often lack immediate geometry in Overpass 'out geom' mode; skip
        continue

geo = { 'type': 'FeatureCollection', 'features': features }
with open(outp, 'w') as fh:
    json.dump(geo, fh)
print('Wrote', outp, file=sys.stderr)

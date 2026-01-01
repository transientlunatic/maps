#!/usr/bin/env python3
"""Generate a gdaldem color file from the QGIS-style color list.

Reads `scripts/hillmap-colours.txt` and outputs a color file suitable for
`gdaldem color-relief`, limited to a range (0..1400 by default) at a
specified increment.

Usage:
  python3 scripts/make_color_ramp.py > data/hillmap-colors-0-1400.txt

Options (environment variables):
  STEP   - increment in metres (default 50)
  MAX    - maximum elevation (default 1400)
  MIN    - minimum elevation (default 0)
"""
import re
import sys
import os

ROOT = os.path.abspath(os.getcwd())
src = os.path.join(ROOT, 'scripts', 'hillmap-colours.txt')
if not os.path.exists(src):
    print('Missing', src, file=sys.stderr)
    sys.exit(2)

step = int(os.environ.get('STEP', '50'))
min_e = int(os.environ.get('MIN', '0'))
max_e = int(os.environ.get('MAX', '1400'))

stops = []
with open(src, 'r') as fh:
    for line in fh:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('INTERPOLATION'):
            continue
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 4:
            continue
        key = parts[0]
        try:
            if key.lower() == 'inf':
                val = float('inf')
            else:
                val = float(re.findall(r"[-+]?[0-9]*\.?[0-9]+", key)[0])
        except Exception:
            continue
        r = int(parts[1]); g = int(parts[2]); b = int(parts[3])
        stops.append((val, (r, g, b)))

stops = sorted(stops, key=lambda x: x[0])
if not stops:
    print('No color stops parsed from', src, file=sys.stderr)
    sys.exit(2)

def interp_color(v):
    # below first
    if v <= stops[0][0]:
        return stops[0][1]
    # above last finite
    finite = [s for s in stops if s[0] != float('inf')]
    if not finite:
        return stops[-1][1]
    if v >= finite[-1][0]:
        return finite[-1][1]
    # find bracketing stops
    lo = finite[0]
    hi = None
    for s in finite:
        if s[0] >= v:
            hi = s
            break
        lo = s
    if hi is None:
        return lo[1]
    if hi[0] == lo[0]:
        return lo[1]
    t = (v - lo[0]) / (hi[0] - lo[0])
    r = int(round(lo[1][0] + t * (hi[1][0] - lo[1][0])))
    g = int(round(lo[1][1] + t * (hi[1][1] - lo[1][1])))
    b = int(round(lo[1][2] + t * (hi[1][2] - lo[1][2])))
    return (r, g, b)

out_lines = []
v = min_e
while v <= max_e:
    r, g, b = interp_color(v)
    out_lines.append(f"{v} {r} {g} {b}")
    v += step

# ensure max_e included
if out_lines and not out_lines[-1].startswith(str(max_e)):
    r, g, b = interp_color(max_e)
    out_lines.append(f"{max_e} {r} {g} {b}")

sys.stdout.write('\n'.join(out_lines) + '\n')

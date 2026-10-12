#!/usr/bin/env python3
"""Add finer colour levels below 200 m to the DEM colour ramp.

Usage:
    python3 scripts/lowland_ramp.py [styling/merged-dem.qml]

The ramp in merged-dem.qml has a single, almost white colour for everything
below 100 m and another for 100-200 m, so in flat country such as Glasgow the
hills disappear. This rewrites the levels from 0 to 200 m as 15 bands (every
10 m up to 100 m, then every 20 m) that run from a pale sage green at sea level
to the beige of the existing 100-200 m band. Levels from 200 m up are not
touched, so mountain areas look as they did.

The file is rewritten in place and the script can be run again, for example after
changing the colours below.
"""
import re
import sys

LOW = (200, 212, 180)    # colour just above sea level
HIGH = (231, 225, 214)   # colour of the 180-200 m band; it meets the 200-300 m band
BREAKS = list(range(10, 101, 10)) + [120, 140, 160, 180, 200]


def band_colour(upper):
    """Colour for the band ending at `upper` metres: LOW at 0 m rising to HIGH at 200 m."""
    t = (upper - 5) / 200 if upper < 200 else 1.0
    return tuple(round(a + (b - a) * t) for a, b in zip(LOW, HIGH))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "styling/merged-dem.qml"
    text = open(path, encoding="utf8").read()

    item = re.compile(r'^ *<item color="#[0-9a-f]{6}" label="[^"]*" value="(\d+)" alpha="255"/>\n', re.M)
    old = [m for m in item.finditer(text) if 0 < int(m.group(1)) <= 200]
    if not old:
        sys.exit("No colour levels between 0 and 200 m found")
    indent = re.match(r" *", old[0].group(0)).group(0)

    lines, previous = [], 0
    for upper in BREAKS:
        r, g, b = band_colour(upper)
        lines.append(
            f'{indent}<item color="#{r:02x}{g:02x}{b:02x}" '
            f'label="{previous:.4f} - {upper:.4f}" value="{upper}" alpha="255"/>\n'
        )
        previous = upper

    start, end = old[0].start(), old[-1].end()
    text = text[:start] + "".join(lines) + text[end:]
    open(path, "w", encoding="utf8").write(text)
    print(f"Rewrote {len(old)} levels as {len(lines)} in {path}")


if __name__ == "__main__":
    main()

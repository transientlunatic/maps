#!/usr/bin/env python3
"""Extract a fill color and symbol alpha from a QGIS QML stylesheet.

Usage: qml_color.py <qml-file>
Prints: R G B A
Where R,G,B are integers 0-255 and A is a float 0..1
"""
import sys
import xml.etree.ElementTree as ET


def parse_qml(path):
    try:
        tree = ET.parse(path)
    except Exception as e:
        print(f"ERROR: cannot parse QML: {e}", file=sys.stderr)
        return 1
    root = tree.getroot()
    # Find first <symbol ... type="fill"> element
    for symbol in root.findall('.//symbol'):
        stype = symbol.get('type')
        if stype and stype.lower() == 'fill':
            # symbol alpha attribute
            alpha_attr = symbol.get('alpha')
            try:
                alpha = float(alpha_attr) if alpha_attr is not None else 1.0
            except Exception:
                alpha = 1.0
            # search for Option name="color" value="r,g,b,a"
            color = None
            for opt in symbol.findall('.//Option'):
                name = opt.get('name')
                if name == 'color' and 'value' in opt.attrib:
                    color = opt.get('value')
                    break
            # fallback: look for prop elements with k="color"
            if color is None:
                for prop in symbol.findall('.//prop'):
                    if prop.get('k') == 'color' and prop.get('v'):
                        color = prop.get('v')
                        break
            if color:
                # color may be 'R,G,B' or 'R,G,B,A' or 'R,G,B,255'
                parts = [p.strip() for p in color.split(',') if p.strip()]
                try:
                    r = int(parts[0])
                    g = int(parts[1])
                    b = int(parts[2])
                except Exception:
                    continue
                a = 255
                if len(parts) >= 4:
                    try:
                        a = int(parts[3])
                    except Exception:
                        a = 255
                # Convert alpha defined in symbol attr as multiplier
                # final alpha = symbol_alpha * (a/255)
                final_alpha = alpha * (a / 255.0)
                print(f"{r} {g} {b} {final_alpha}")
                return 0
    # If not found, default to opaque magenta for debugging
    print("255 0 255 1.0")
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: qml_color.py <qml-file>", file=sys.stderr)
        sys.exit(2)
    sys.exit(parse_qml(sys.argv[1]))

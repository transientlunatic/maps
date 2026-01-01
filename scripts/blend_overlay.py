#!/usr/bin/env python3
"""Blend overlay masks onto a basemap using QML colors.

This script blends water and forest overlay masks onto a shaded basemap,
using colors extracted from QGIS QML style files.

Usage:
    blend_overlay.py <basemap.tif> <water_mask.tif> <forest_mask.tif> <water.qml> <forest.qml> <output.tif>
"""
import sys
import subprocess
import os


def run_command(cmd, description=""):
    """Run a shell command and check for errors."""
    if description:
        print(f"{description}")
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def get_qml_color(qml_file):
    """Extract R, G, B, Alpha from QML file."""
    result = run_command(['python3', 'scripts/qml_color.py', qml_file], "")
    parts = result.strip().split()
    return {
        'r': int(parts[0]),
        'g': int(parts[1]),
        'b': int(parts[2]),
        'a': float(parts[3])
    }


def blend_overlays(basemap, water_mask, forest_mask, water_qml, forest_qml, output):
    """Blend water and forest overlays onto basemap."""
    
    # Extract colors from QML files
    print("Extracting colors from QML files...")
    water_color = get_qml_color(water_qml)
    forest_color = get_qml_color(forest_qml)
    
    print(f"Water color: R={water_color['r']} G={water_color['g']} B={water_color['b']} Alpha={water_color['a']}")
    print(f"Forest color: R={forest_color['r']} G={forest_color['g']} B={forest_color['b']} Alpha={forest_color['a']}")
    
    # Create temp directory
    os.makedirs('data/tmp', exist_ok=True)
    
    # Process each band (R, G, B)
    for band_idx, band_name in enumerate(['b1', 'b2', 'b3'], start=1):
        print(f"\nProcessing band {band_idx} ({band_name})...")
        
        # Get color components for this band
        if band_name == 'b1':
            water_val = water_color['r']
            forest_val = forest_color['r']
        elif band_name == 'b2':
            water_val = water_color['g']
            forest_val = forest_color['g']
        else:  # b3
            water_val = water_color['b']
            forest_val = forest_color['b']
        
        forest_alpha = forest_color['a']
        
        # Step 1: Blend water onto basemap
        # Result = (1-W)*base + W*water_color
        step_file = f'data/tmp/step_{band_name}.tif'
        run_command([
            'gdal_calc.py',
            '-A', basemap, f'--A_band={band_idx}',
            '-B', water_mask,
            '--outfile', step_file,
            f'--calc=(1-B)*A + B*{water_val}',
            '--type=Byte',
            '--overwrite'
        ], f"Blending water into band {band_idx}...")
        
        # Step 2: Blend forest onto the result
        # Result = (1 - F*alpha)*step + F*alpha*forest_color
        final_file = f'data/tmp/final_{band_name}.tif'
        run_command([
            'gdal_calc.py',
            '-A', step_file, '--A_band=1',
            '-B', forest_mask,
            '--outfile', final_file,
            f'--calc=(1 - B*{forest_alpha})*A + B*{forest_alpha}*{forest_val}',
            '--type=Byte',
            '--overwrite'
        ], f"Blending forest into band {band_idx}...")
    
    # Merge the three bands into a single RGB image
    print("\nMerging bands into final RGB image...")
    temp_output = f'{output}.tmp'
    run_command([
        'gdal_merge.py',
        '-separate',
        '-o', temp_output,
        'data/tmp/final_b1.tif',
        'data/tmp/final_b2.tif',
        'data/tmp/final_b3.tif'
    ], "Merging RGB bands...")
    
    # Compress and tile the output
    print("Compressing final output...")
    run_command([
        'gdal_translate',
        '-co', 'COMPRESS=LZW',
        '-co', 'TILED=YES',
        temp_output, output
    ], "Compressing...")
    
    # Remove temp file
    os.remove(temp_output)
    
    print(f"\nSuccess! Created {output}")


def main():
    if len(sys.argv) != 7:
        print(__doc__)
        sys.exit(1)
    
    basemap = sys.argv[1]
    water_mask = sys.argv[2]
    forest_mask = sys.argv[3]
    water_qml = sys.argv[4]
    forest_qml = sys.argv[5]
    output = sys.argv[6]
    
    blend_overlays(basemap, water_mask, forest_mask, water_qml, forest_qml, output)


if __name__ == '__main__':
    main()

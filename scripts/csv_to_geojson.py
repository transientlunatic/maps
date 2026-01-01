#!/usr/bin/env python3
"""Convert CSV files with latitude/longitude to GeoJSON.

Usage:
    csv_to_geojson.py <input.csv> <output.geojson> --lat-col <lat_column> --lon-col <lon_column> [--name-col <name_column>]

Reads a CSV file with geographic coordinates and converts it to GeoJSON format.
"""
import csv
import json
import sys
import argparse


def csv_to_geojson(input_csv, output_geojson, lat_col, lon_col, name_col=None):
    """Convert CSV to GeoJSON.
    
    Args:
        input_csv: Path to input CSV file
        output_geojson: Path to output GeoJSON file
        lat_col: Name of latitude column
        lon_col: Name of longitude column
        name_col: Optional name of column to use as feature name
    """
    features = []
    
    with open(input_csv, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            try:
                lat = float(row[lat_col])
                lon = float(row[lon_col])
                
                # Create properties from all columns
                properties = dict(row)
                
                # Add name property if specified
                if name_col and name_col in row:
                    properties['name'] = row[name_col]
                
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat]
                    },
                    "properties": properties
                }
                features.append(feature)
                
            except (ValueError, KeyError) as e:
                # Skip rows with invalid coordinates
                print(f"Warning: Skipping row due to error: {e}", file=sys.stderr)
                continue
    
    geojson = {
        "type": "FeatureCollection",
        "features": features
    }
    
    with open(output_geojson, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, indent=2)
    
    print(f"Converted {len(features)} features to {output_geojson}")


def main():
    parser = argparse.ArgumentParser(
        description='Convert CSV with coordinates to GeoJSON'
    )
    parser.add_argument('input_csv', help='Input CSV file')
    parser.add_argument('output_geojson', help='Output GeoJSON file')
    parser.add_argument('--lat-col', required=True, help='Latitude column name')
    parser.add_argument('--lon-col', required=True, help='Longitude column name')
    parser.add_argument('--name-col', help='Optional name column')
    
    args = parser.parse_args()
    
    csv_to_geojson(
        args.input_csv,
        args.output_geojson,
        args.lat_col,
        args.lon_col,
        args.name_col
    )


if __name__ == '__main__':
    main()

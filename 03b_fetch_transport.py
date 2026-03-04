#!/usr/bin/env python3
"""Fetch London transport line geometry and station data from the TfL Unified API.

Produces:
  data/london_lines.json    – GeoJSON FeatureCollection of route geometries
  data/london_stations.json – station list with modes and lines fields
"""

import csv
import json
import time
from pathlib import Path

import requests

DATA_DIR = Path("data")

TFL_BASE = "https://api.tfl.gov.uk"
MODES = "tube,dlr,overground,elizabeth-line,tram,national-rail"

LINE_COLORS = {
    "bakerloo": "#B36305",
    "central": "#E32017",
    "circle": "#FFD300",
    "district": "#00782A",
    "elizabeth": "#6950A1",
    "hammersmith-city": "#F3A9BB",
    "jubilee": "#A0A5A9",
    "metropolitan": "#9B0056",
    "northern": "#000000",
    "piccadilly": "#003688",
    "victoria": "#0098D4",
    "waterloo-city": "#95CDBA",
    "dlr": "#00A4A7",
    # Overground lines (all orange)
    "lioness": "#EE7C0E",
    "mildmay": "#EE7C0E",
    "windrush": "#EE7C0E",
    "weaver": "#EE7C0E",
    "suffragette": "#EE7C0E",
    "liberty": "#EE7C0E",
    "london-overground": "#EE7C0E",
    # Tram
    "tram": "#84B817",
    # National Rail — use generic rail red for all lines
}

# National Rail lines all get the same color
NATIONAL_RAIL_COLOR = "#E21836"

# Default color for any line not in the map
DEFAULT_COLOR = "#888888"

MODE_COLORS = {
    "tube": None,  # uses line color
    "dlr": "#00A4A7",
    "overground": "#EE7C0E",
    "elizabeth-line": "#6950A1",
    "tram": "#84B817",
    "national-rail": "#E21836",
}


def fetch_lines():
    """Get all lines for configured modes."""
    url = f"{TFL_BASE}/Line/Mode/{MODES}"
    print(f"Fetching lines: {url}")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_route_sequence(line_id):
    """Get the outbound route sequence with geometry for a line."""
    url = f"{TFL_BASE}/Line/{line_id}/Route/Sequence/outbound"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def parse_line_strings(raw_line_strings):
    """Parse TfL lineStrings into coordinate arrays for GeoJSON MultiLineString.

    TfL returns lineStrings as JSON-encoded arrays of [lon, lat] pairs.
    """
    coordinates = []
    for ls in raw_line_strings:
        try:
            parsed = json.loads(ls)
            # TfL wraps each lineString as [ [ [lon,lat], ... ] ]
            # so parsed is a list of line arrays — extend to flatten one level
            if parsed and isinstance(parsed[0], list) and isinstance(parsed[0][0], list):
                coordinates.extend(parsed)
            elif parsed and isinstance(parsed[0], list):
                coordinates.append(parsed)
            else:
                coordinates.append([parsed])
        except (json.JSONDecodeError, TypeError):
            continue
    return coordinates


def main():
    DATA_DIR.mkdir(exist_ok=True)

    # Step 1: Get all lines
    lines_data = fetch_lines()
    print(f"Found {len(lines_data)} lines")

    features = []
    # station_key -> {name, lat, lon, modes: set, lines: set}
    stations_map = {}

    # Step 2: For each line, get route sequence
    for i, line in enumerate(lines_data):
        line_id = line["id"]
        line_name = line["name"]
        mode = line["modeName"]
        if mode == "national-rail":
            color = LINE_COLORS.get(line_id, NATIONAL_RAIL_COLOR)
        else:
            color = LINE_COLORS.get(line_id, DEFAULT_COLOR)

        print(f"  [{i+1}/{len(lines_data)}] {line_name} ({mode})...")

        try:
            route = fetch_route_sequence(line_id)
        except requests.RequestException as e:
            print(f"    Error fetching route for {line_id}: {e}")
            time.sleep(0.5)
            continue

        # Parse geometry
        raw_line_strings = route.get("lineStrings", [])
        coordinates = parse_line_strings(raw_line_strings)

        if coordinates:
            feature = {
                "type": "Feature",
                "properties": {
                    "id": line_id,
                    "name": line_name,
                    "mode": mode,
                    "color": color,
                },
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": coordinates,
                },
            }
            features.append(feature)

        # Collect stations
        for stop_group in route.get("stopPointSequences", []):
            for sp in stop_group.get("stopPoint", []):
                key = f"{sp['lat']:.5f},{sp['lon']:.5f}"
                if key not in stations_map:
                    stations_map[key] = {
                        "name": sp["name"],
                        "lat": sp["lat"],
                        "lon": sp["lon"],
                        "modes": set(),
                        "lines": set(),
                    }
                stations_map[key]["modes"].add(mode)
                stations_map[key]["lines"].add(line_id)

        time.sleep(0.5)

    # Step 3: Save outputs
    # Filter line geometry to London area
    LONDON_BOUNDS = (51.28, 51.70, -0.52, 0.34)

    def segment_in_london(segment):
        """Check if any coordinate in a segment falls within London bounds."""
        for lon, lat in segment:
            if (LONDON_BOUNDS[0] <= lat <= LONDON_BOUNDS[1]
                    and LONDON_BOUNDS[2] <= lon <= LONDON_BOUNDS[3]):
                return True
        return False

    for feature in features:
        coords = feature["geometry"]["coordinates"]
        feature["geometry"]["coordinates"] = [
            seg for seg in coords if segment_in_london(seg)
        ]
    features = [f for f in features if f["geometry"]["coordinates"]]

    # GeoJSON line geometry
    geojson = {"type": "FeatureCollection", "features": features}
    lines_path = DATA_DIR / "london_lines.json"
    lines_path.write_text(json.dumps(geojson, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(features)} line features to {lines_path}")

    # Filter stations to Greater London area only
    LONDON_BOUNDS = (51.28, 51.70, -0.52, 0.34)  # (min_lat, max_lat, min_lon, max_lon)
    before = len(stations_map)
    stations_map = {
        k: v
        for k, v in stations_map.items()
        if LONDON_BOUNDS[0] <= v["lat"] <= LONDON_BOUNDS[1]
        and LONDON_BOUNDS[2] <= v["lon"] <= LONDON_BOUNDS[3]
    }
    print(f"Filtered stations to London bounds: {before} -> {len(stations_map)}")

    # Merge in CSV stations that weren't found via TfL API
    csv_path = DATA_DIR / "london_stations.csv"
    csv_added = 0
    if csv_path.exists():
        with open(csv_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                lat = float(row["Latitude"])
                lon = float(row["Longitude"])
                key = f"{lat:.5f},{lon:.5f}"
                if key not in stations_map:
                    stations_map[key] = {
                        "name": row["Station"],
                        "lat": lat,
                        "lon": lon,
                        "modes": {"national-rail"},
                        "lines": set(),
                    }
                    csv_added += 1
        print(f"Merged {csv_added} additional stations from CSV")

    # Stations with modes/lines
    stations_list = []
    for st in sorted(stations_map.values(), key=lambda s: s["name"]):
        stations_list.append(
            {
                "name": st["name"],
                "lat": st["lat"],
                "lon": st["lon"],
                "modes": sorted(st["modes"]),
                "lines": sorted(st["lines"]),
            }
        )
    stations_path = DATA_DIR / "london_stations.json"
    stations_path.write_text(
        json.dumps(stations_list, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Wrote {len(stations_list)} stations to {stations_path}")


if __name__ == "__main__":
    main()

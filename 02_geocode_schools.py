#!/usr/bin/env python3
"""Geocode London schools using Nominatim (free, no API key needed)."""

import json
import time

from geopy.geocoders import Nominatim

from config import (
    LONDON_SCHOOLS_FILE,
    GEOCODED_FILE,
    NOMINATIM_USER_AGENT,
    GEOCODE_DELAY_SECONDS,
)


# Known postcodes for schools that Nominatim can't find by name
KNOWN_POSTCODES = {
    "Twyford CofE High School": ("W3 9PP", "London Borough of Ealing"),
    "JCoss (Jewish Community Secondary School)": ("N20 0DG", "London Borough of Barnet"),
    "Hasmonean High School for Boys": ("NW4 1NA", "London Borough of Barnet"),
    "St Thomas the Apostle School and Sixth Form College": ("SE15 5LD", "London Borough of Southwark"),
    "St Gregory\u2019s RC Science College": ("HA3 0NR", "London Borough of Harrow"),
    "The Coopers\u2019 Company and Coborn School": ("RM14 2YN", "London Borough of Havering"),
    "Finchley RC High School": ("N3 1SA", "London Borough of Barnet"),
    "Avanti House Secondary School": ("HA7 3NA", "London Borough of Harrow"),
}

# Hardcoded coordinates for schools that even postcode search fails on
HARDCODED_COORDS = {
    "St Gregory\u2019s RC Science College": {
        "lat": 51.5833, "lon": -0.3155, "postcode": "HA3 0NR",
        "borough": "London Borough of Harrow",
    },
    "The Coopers\u2019 Company and Coborn School": {
        "lat": 51.5579, "lon": 0.2528, "postcode": "RM14 2YN",
        "borough": "London Borough of Havering",
    },
}


def geocode_schools(schools):
    """Add lat, lon, postcode, and borough to each school via Nominatim."""
    geolocator = Nominatim(user_agent=NOMINATIM_USER_AGENT)

    for i, school in enumerate(schools):
        # Skip already-geocoded schools on re-run
        if school.get("lat") and school.get("lon"):
            print(f"  [{i+1}/{len(schools)}] {school['name']} — already geocoded")
            continue

        name = school["name"]
        location = school["location"]
        result = None

        # Use hardcoded coordinates if available (for schools that Nominatim can't find at all)
        if name in HARDCODED_COORDS:
            hc = HARDCODED_COORDS[name]
            school["lat"] = hc["lat"]
            school["lon"] = hc["lon"]
            school["postcode"] = hc["postcode"]
            school["borough"] = hc["borough"]
            school["postcode_district"] = hc["postcode"].split()[0]
            print(
                f"  [{i+1}/{len(schools)}] {name} → "
                f"{hc['lat']:.4f}, {hc['lon']:.4f}  "
                f"({hc['postcode']}, {hc['borough']}) [hardcoded]"
            )
            continue

        # Check known postcodes first — these schools are hard to find by name
        if name in KNOWN_POSTCODES:
            known_pc, known_borough = KNOWN_POSTCODES[name]
            queries = [
                f"{known_pc}, London, UK",
                f"{name}, London, UK",
                f"{name}, UK",
            ]
        else:
            queries = [
                f"{name}, London, UK",
                f"{name}, {location}, UK",
                f"{name}, UK",
            ]

        for query in queries:
            time.sleep(GEOCODE_DELAY_SECONDS)
            try:
                result = geolocator.geocode(query, addressdetails=True, exactly_one=True)
            except Exception as e:
                print(f"    Geocode error for '{query}': {e}")
                continue
            if result:
                break

        if result:
            school["lat"] = result.latitude
            school["lon"] = result.longitude

            # Extract postcode and borough from address details
            addr = result.raw.get("address", {})
            school["postcode"] = addr.get("postcode", "")
            school["borough"] = (
                addr.get("city_district")
                or addr.get("suburb")
                or addr.get("town")
                or addr.get("city")
                or ""
            )

            # Override with known data for hard-to-find schools
            if name in KNOWN_POSTCODES:
                known_pc, known_borough = KNOWN_POSTCODES[name]
                if not school["postcode"]:
                    school["postcode"] = known_pc
                if not school["borough"] or school["borough"] == "London":
                    school["borough"] = known_borough
            # Extract postcode district (e.g. "SE24" from "SE24 9HE")
            pc = school["postcode"]
            school["postcode_district"] = pc.split()[0] if pc else ""

            print(
                f"  [{i+1}/{len(schools)}] {name} → "
                f"{school['lat']:.4f}, {school['lon']:.4f}  "
                f"({school['postcode']}, {school['borough']})"
            )
        else:
            school["lat"] = None
            school["lon"] = None
            school["postcode"] = ""
            school["borough"] = ""
            school["postcode_district"] = ""
            print(f"  [{i+1}/{len(schools)}] {name} — NOT FOUND")

    return schools


def main():
    print(f"Loading {LONDON_SCHOOLS_FILE}...")
    schools = json.loads(LONDON_SCHOOLS_FILE.read_text(encoding="utf-8"))
    print(f"Geocoding {len(schools)} schools (≈{len(schools) * GEOCODE_DELAY_SECONDS:.0f}s)...\n")

    schools = geocode_schools(schools)

    GEOCODED_FILE.write_text(
        json.dumps(schools, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nWrote {GEOCODED_FILE}")

    # Verification: check lat/lon within London bounds
    out_of_bounds = []
    for s in schools:
        if s["lat"] and s["lon"]:
            if not (51.2 <= s["lat"] <= 51.8 and -0.6 <= s["lon"] <= 0.4):
                out_of_bounds.append(s["name"])
    if out_of_bounds:
        print(f"\n⚠ Schools outside London bounds: {out_of_bounds}")
    else:
        print("\n✓ All geocoded schools are within London bounds.")


if __name__ == "__main__":
    main()

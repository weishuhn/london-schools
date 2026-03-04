#!/usr/bin/env python3
"""Combine schools, geocoding, neighbourhoods, and property data into a final report."""

import csv
import json

from config import (
    GEOCODED_FILE,
    NEIGHBOURHOODS_FILE,
    PROPERTIES_DIR,
    COMBINED_JSON,
    COMBINED_CSV,
)


def load_property_summary(school_name):
    """Load property results for a school and return summary stats."""
    safe_name = school_name.replace("/", "_").replace(" ", "_").replace("'", "")
    filepath = PROPERTIES_DIR / f"{safe_name}.json"

    if not filepath.exists():
        return {"property_count": 0, "avg_price": None, "min_price": None, "max_price": None}

    properties = json.loads(filepath.read_text(encoding="utf-8"))
    if not properties:
        return {"property_count": 0, "avg_price": None, "min_price": None, "max_price": None}

    prices = []
    for p in properties:
        price = p.get("price") or p.get("asking_price")
        if price and isinstance(price, (int, float)):
            prices.append(price)
        elif price and isinstance(price, str):
            # Strip "£" and commas, try to parse
            cleaned = price.replace("£", "").replace(",", "").strip()
            try:
                prices.append(float(cleaned))
            except ValueError:
                pass

    return {
        "property_count": len(properties),
        "avg_price": round(sum(prices) / len(prices)) if prices else None,
        "min_price": min(prices) if prices else None,
        "max_price": max(prices) if prices else None,
    }


def build_neighbourhood_lookup(neighbourhoods):
    """Create a lookup from borough → neighbourhood data."""
    return {n["borough"]: n for n in neighbourhoods}


def main():
    print(f"Loading geocoded schools from {GEOCODED_FILE}...")
    schools = json.loads(GEOCODED_FILE.read_text(encoding="utf-8"))

    neighbourhoods = []
    if NEIGHBOURHOODS_FILE.exists():
        neighbourhoods = json.loads(NEIGHBOURHOODS_FILE.read_text(encoding="utf-8"))
    hood_lookup = build_neighbourhood_lookup(neighbourhoods)

    # Build combined report
    combined = []
    for s in schools:
        borough = s.get("borough", "")
        hood = hood_lookup.get(borough, {})
        props = load_property_summary(s["name"])

        entry = {
            **s,
            "neighbourhood_composite_score": hood.get("composite_score"),
            "neighbourhood_avg_gcse": hood.get("avg_gcse_pct_7_9"),
            "neighbourhood_school_count": hood.get("school_count"),
            **props,
        }
        combined.append(entry)

    # Write JSON
    COMBINED_JSON.write_text(
        json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {COMBINED_JSON}")

    # Write CSV (flat, one row per school)
    csv_fields = [
        "rank", "name", "location", "lat", "lon", "borough", "postcode",
        "postcode_district", "type", "gcse_pct_7_9", "gcse_rank",
        "alevel_pct_a_star", "alevel_pct_a_star_a", "alevel_pct_a_star_b",
        "alevel_rank", "gender", "neighbourhood_composite_score",
        "neighbourhood_avg_gcse", "neighbourhood_school_count",
        "property_count", "avg_price", "min_price", "max_price",
    ]

    with open(COMBINED_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(combined)

    print(f"Wrote {COMBINED_CSV}")
    print(f"\n{len(combined)} schools in final report.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Analyse neighbourhoods by grouping schools by borough and postcode district."""

import json
from collections import defaultdict

from config import GEOCODED_FILE, NEIGHBOURHOODS_FILE


def analyse_neighbourhoods(schools):
    """Group schools by borough and postcode district, compute summary stats."""
    by_borough = defaultdict(list)
    by_postcode = defaultdict(list)

    for s in schools:
        borough = s.get("borough", "Unknown")
        pc_district = s.get("postcode_district", "Unknown")
        if borough:
            by_borough[borough].append(s)
        if pc_district:
            by_postcode[pc_district].append(s)

    neighbourhoods = []

    for borough, group in sorted(by_borough.items()):
        gcse_scores = [s["gcse_pct_7_9"] for s in group if s.get("gcse_pct_7_9")]
        alevel_scores = [s["alevel_pct_a_star_b"] for s in group if s.get("alevel_pct_a_star_b")]
        types = list({s["type"] for s in group})
        genders = list({s["gender"] for s in group})
        postcodes = list({s.get("postcode_district", "") for s in group if s.get("postcode_district")})

        avg_gcse = sum(gcse_scores) / len(gcse_scores) if gcse_scores else 0
        avg_alevel = sum(alevel_scores) / len(alevel_scores) if alevel_scores else 0

        # Composite score: (school_count × 10) + avg_gcse_pct
        composite = len(group) * 10 + avg_gcse

        neighbourhoods.append({
            "borough": borough,
            "postcode_districts": sorted(postcodes),
            "school_count": len(group),
            "schools": [s["name"] for s in group],
            "avg_gcse_pct_7_9": round(avg_gcse, 1),
            "avg_alevel_pct_a_star_b": round(avg_alevel, 1),
            "school_types": sorted(types),
            "gender_mix": sorted(genders),
            "composite_score": round(composite, 1),
        })

    # Sort by composite score descending
    neighbourhoods.sort(key=lambda n: n["composite_score"], reverse=True)
    return neighbourhoods


def main():
    print(f"Loading {GEOCODED_FILE}...")
    schools = json.loads(GEOCODED_FILE.read_text(encoding="utf-8"))
    print(f"Analysing neighbourhoods for {len(schools)} schools...\n")

    neighbourhoods = analyse_neighbourhoods(schools)

    for n in neighbourhoods:
        print(
            f"  {n['borough']:30s}  "
            f"schools={n['school_count']}  "
            f"avg_gcse={n['avg_gcse_pct_7_9']:5.1f}%  "
            f"composite={n['composite_score']:5.1f}"
        )

    NEIGHBOURHOODS_FILE.write_text(
        json.dumps(neighbourhoods, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nWrote {NEIGHBOURHOODS_FILE}")


if __name__ == "__main__":
    main()

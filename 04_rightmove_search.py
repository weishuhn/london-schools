#!/usr/bin/env python3
"""Search Rightmove for properties near each London school using Scrapfly.

Strategy: resolve postcode districts to Rightmove OUTCODE identifiers via the
house-prices page, then use the JSON listing API for property search.
"""

import asyncio
import json
import re
import sys
from urllib.parse import urlencode

from scrapfly import ScrapeConfig, ScrapflyClient

from config import (
    GEOCODED_FILE,
    PROPERTIES_DIR,
    SCRAPFLY_KEY,
    SEARCH_RADIUS_MILES,
    MAX_PROPERTIES_PER_SCHOOL,
    MIN_BEDROOMS,
    MAX_BEDROOMS,
    MIN_PRICE,
    MAX_PRICE,
)

if not SCRAPFLY_KEY:
    print("Error: SCRAPFLY_KEY not set in config.py.")
    sys.exit(1)

SCRAPFLY = ScrapflyClient(key=SCRAPFLY_KEY)
BASE_CONFIG = {"asp": True, "country": "GB"}

RADIUS_MAP = {0.25: "0.25", 0.5: "0.5", 1.0: "1.0", 2.0: "2.0"}
RM_RADIUS = RADIUS_MAP.get(SEARCH_RADIUS_MILES, "0.5")

# Cache: postcode_district → OUTCODE identifier
_outcode_cache = {}


def safe_filename(name):
    """Convert school name to a safe filename."""
    return name.replace("/", "_").replace(" ", "_").replace("\u2019", "")


async def resolve_outcode(postcode_district):
    """Resolve a postcode district (e.g. 'SE24') to a Rightmove OUTCODE identifier.

    Fetches the house-prices page which embeds the OUTCODE^{id} in its HTML.
    """
    if postcode_district in _outcode_cache:
        return _outcode_cache[postcode_district]

    url = f"https://www.rightmove.co.uk/house-prices/{postcode_district}.html"
    try:
        result = await SCRAPFLY.async_scrape(
            ScrapeConfig(url, raise_on_upstream_error=False, **BASE_CONFIG)
        )
        if result.upstream_status_code != 200:
            print(f"    house-prices page returned {result.upstream_status_code} for {postcode_district}")
            _outcode_cache[postcode_district] = None
            return None

        match = re.search(r'OUTCODE\^(\d+)', result.content)
        if match:
            outcode_id = f"OUTCODE^{match.group(1)}"
            _outcode_cache[postcode_district] = outcode_id
            return outcode_id
    except Exception as e:
        print(f"    Error resolving outcode for {postcode_district}: {e}")

    _outcode_cache[postcode_district] = None
    return None


async def search_properties(outcode_id, postcode, max_results=50):
    """Search Rightmove for BUY properties near an OUTCODE location."""
    params = {
        "searchLocation": postcode,
        "useLocationIdentifier": True,
        "locationIdentifier": outcode_id,
        "radius": RM_RADIUS,
        "_includeSSTC": True,
        "index": 0,
        "sortType": "6",
        "channel": "BUY",
        "transactionType": "BUY",
    }
    if MIN_BEDROOMS is not None:
        params["minBedrooms"] = MIN_BEDROOMS
    if MAX_BEDROOMS is not None:
        params["maxBedrooms"] = MAX_BEDROOMS
    if MIN_PRICE is not None:
        params["minPrice"] = MIN_PRICE
    if MAX_PRICE is not None:
        params["maxPrice"] = MAX_PRICE

    url = "https://www.rightmove.co.uk/api/property-search/listing/search?" + urlencode(params)
    result = await SCRAPFLY.async_scrape(ScrapeConfig(url, **BASE_CONFIG))
    data = json.loads(result.content)

    properties = data.get("properties", [])
    total = int(data.get("resultCount", "0").replace(",", ""))
    print(f"    Found {total} total properties, keeping up to {max_results}")

    # Paginate if needed (24 results per page)
    for offset in range(24, min(max_results, total), 24):
        params["index"] = offset
        page_url = "https://www.rightmove.co.uk/api/property-search/listing/search?" + urlencode(params)
        try:
            page_result = await SCRAPFLY.async_scrape(ScrapeConfig(page_url, **BASE_CONFIG))
            page_data = json.loads(page_result.content)
            properties.extend(page_data.get("properties", []))
        except Exception as e:
            print(f"    Pagination error at offset {offset}: {e}")
            break

    return properties[:max_results]


def slim_property(p):
    """Extract key fields from a Rightmove property object."""
    price_obj = p.get("price", {})
    if isinstance(price_obj, dict):
        price = price_obj.get("amount")
        display_prices = price_obj.get("displayPrices", [])
        price_display = display_prices[0].get("displayPrice") if display_prices else None
    else:
        price = price_obj
        price_display = None

    loc = p.get("location", {})
    return {
        "id": p.get("id"),
        "price": price,
        "price_display": price_display,
        "address": p.get("displayAddress"),
        "property_type": p.get("propertySubType"),
        "bedrooms": p.get("bedrooms"),
        "bathrooms": p.get("bathrooms"),
        "summary": p.get("summary"),
        "url": f"https://www.rightmove.co.uk/properties/{p['id']}" if p.get("id") else None,
        "latitude": loc.get("latitude") if isinstance(loc, dict) else None,
        "longitude": loc.get("longitude") if isinstance(loc, dict) else None,
    }


async def scrape_school(school):
    """Search Rightmove for properties near a single school."""
    name = school["name"]
    postcode = school.get("postcode", "")
    pc_district = school.get("postcode_district", "")

    if not postcode or not pc_district:
        print(f"  {name} — no postcode, skipping")
        return

    outfile = PROPERTIES_DIR / f"{safe_filename(name)}.json"
    if outfile.exists():
        existing = json.loads(outfile.read_text(encoding="utf-8"))
        if existing:
            print(f"  {name} — already scraped ({len(existing)} properties)")
            return

    print(f"  {name} ({pc_district})")

    try:
        outcode_id = await resolve_outcode(pc_district)
        if not outcode_id:
            print(f"    Could not resolve OUTCODE for {pc_district}")
            outfile.write_text("[]", encoding="utf-8")
            return

        print(f"    {outcode_id}")
        properties = await search_properties(outcode_id, postcode, MAX_PROPERTIES_PER_SCHOOL)

        # Deduplicate and slim
        seen = set()
        slim = []
        for p in properties:
            pid = p.get("id")
            if pid and pid in seen:
                continue
            if pid:
                seen.add(pid)
            slim.append(slim_property(p))
            if len(slim) >= MAX_PROPERTIES_PER_SCHOOL:
                break

        outfile.write_text(
            json.dumps(slim, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"    Saved {len(slim)} properties")

    except Exception as e:
        print(f"    Error: {e}")
        outfile.write_text("[]", encoding="utf-8")


async def main():
    print(f"Loading {GEOCODED_FILE}...")
    schools = json.loads(GEOCODED_FILE.read_text(encoding="utf-8"))

    filters = []
    if MIN_BEDROOMS is not None:
        filters.append(f"min {MIN_BEDROOMS} beds")
    if MAX_BEDROOMS is not None:
        filters.append(f"max {MAX_BEDROOMS} beds")
    if MIN_PRICE is not None:
        filters.append(f"min \u00a3{MIN_PRICE:,}")
    if MAX_PRICE is not None:
        filters.append(f"max \u00a3{MAX_PRICE:,}")
    filter_str = f" | Filters: {', '.join(filters)}" if filters else ""
    print(f"Searching Rightmove for {len(schools)} schools{filter_str}\n")

    for school in schools:
        await scrape_school(school)

    print(f"\nDone. Results in {PROPERTIES_DIR}/")


if __name__ == "__main__":
    asyncio.run(main())

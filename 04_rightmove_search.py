#!/usr/bin/env python3
"""Search Rightmove for properties near each London school using Playwright.

Strategy: resolve full postcodes to Rightmove POSTCODE identifiers via the
house-prices page, then use the JSON listing API for property search.
"""

import asyncio
import json
import re
import sys
from urllib.parse import urlencode

from playwright.async_api import async_playwright

from config import (
    GEOCODED_FILE,
    PROPERTIES_DIR,
    SEARCH_RADIUS_MILES,
    MAX_PROPERTIES_PER_SCHOOL,
    MIN_BEDROOMS,
    MAX_BEDROOMS,
    MIN_PRICE,
    MAX_PRICE,
)

RADIUS_MAP = {0.25: "0.25", 0.5: "0.5", 1.0: "1.0", 2.0: "2.0"}
RM_RADIUS = RADIUS_MAP.get(SEARCH_RADIUS_MILES, "0.5")

# Cache: postcode → POSTCODE identifier
_postcode_cache = {}

REQUEST_DELAY = 1.5  # seconds between requests


def safe_filename(name):
    """Convert school name to a safe filename."""
    return name.replace("/", "_").replace(" ", "_").replace("\u2019", "")


async def resolve_postcode(page, postcode):
    """Resolve a full postcode (e.g. 'W6 9LP') to a Rightmove POSTCODE identifier.

    Fetches the house-prices page which embeds the POSTCODE^{id} in its HTML.
    """
    if postcode in _postcode_cache:
        return _postcode_cache[postcode]

    # Rightmove URL format: "W6 9LP" → "W6-9LP"
    slug = postcode.replace(" ", "-")
    url = f"https://www.rightmove.co.uk/house-prices/{slug}.html"
    try:
        response = await page.goto(url, wait_until="domcontentloaded")
        if response and response.status != 200:
            print(f"    house-prices page returned {response.status} for {postcode}")
            _postcode_cache[postcode] = None
            return None

        content = await page.content()
        match = re.search(r'POSTCODE\^(\d+)', content)
        if match:
            postcode_id = f"POSTCODE^{match.group(1)}"
            _postcode_cache[postcode] = postcode_id
            return postcode_id
    except Exception as e:
        print(f"    Error resolving postcode for {postcode}: {e}")

    _postcode_cache[postcode] = None
    return None


async def search_properties(page, postcode_id, postcode, max_results=50):
    """Search Rightmove for BUY properties near a POSTCODE location."""
    params = {
        "searchLocation": postcode,
        "useLocationIdentifier": True,
        "locationIdentifier": postcode_id,
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
    await asyncio.sleep(REQUEST_DELAY)
    response = await page.goto(url, wait_until="domcontentloaded")
    body = await response.text()
    data = json.loads(body)

    properties = data.get("properties", [])
    total = int(data.get("resultCount", "0").replace(",", ""))
    print(f"    Found {total} total properties, keeping up to {max_results}")

    # Paginate if needed (24 results per page)
    for offset in range(24, min(max_results, total), 24):
        params["index"] = offset
        page_url = "https://www.rightmove.co.uk/api/property-search/listing/search?" + urlencode(params)
        try:
            await asyncio.sleep(REQUEST_DELAY)
            resp = await page.goto(page_url, wait_until="domcontentloaded")
            page_body = await resp.text()
            page_data = json.loads(page_body)
            properties.extend(page_data.get("properties", []))
        except Exception as e:
            print(f"    Pagination error at offset {offset}: {e}")
            break

    return properties[:max_results]


def rightmove_search_url(postcode_id, postcode):
    """Build a Rightmove website search URL for the given postcode."""
    params = {
        "searchLocation": postcode,
        "locationIdentifier": postcode_id,
        "radius": RM_RADIUS,
        "sortType": "6",
        "propertyTypes": "",
        "includeSSTC": "false",
        "mustHave": "",
        "dontShow": "",
        "furnishTypes": "",
        "keywords": "",
    }
    if MIN_BEDROOMS is not None:
        params["minBedrooms"] = MIN_BEDROOMS
    if MAX_BEDROOMS is not None:
        params["maxBedrooms"] = MAX_BEDROOMS
    if MIN_PRICE is not None:
        params["minPrice"] = MIN_PRICE
    if MAX_PRICE is not None:
        params["maxPrice"] = MAX_PRICE
    return "https://www.rightmove.co.uk/property-for-sale/find.html?" + urlencode(params)


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

    # Extract main thumbnail image
    prop_images = p.get("propertyImages") or {}
    image_url = prop_images.get("mainImageSrc")
    if not image_url:
        images_list = prop_images.get("images") or p.get("images") or []
        if images_list:
            image_url = images_list[0].get("srcUrl")

    return {
        "id": p.get("id"),
        "price": price,
        "price_display": price_display,
        "address": p.get("displayAddress"),
        "property_type": p.get("propertySubType"),
        "bedrooms": p.get("bedrooms"),
        "bathrooms": p.get("bathrooms"),
        "summary": p.get("summary"),
        "image_url": image_url,
        "url": f"https://www.rightmove.co.uk/properties/{p['id']}" if p.get("id") else None,
        "latitude": loc.get("latitude") if isinstance(loc, dict) else None,
        "longitude": loc.get("longitude") if isinstance(loc, dict) else None,
    }


async def scrape_school(page, school):
    """Search Rightmove for properties near a single school."""
    name = school["name"]
    postcode = school.get("postcode", "")

    if not postcode:
        print(f"  {name} — no postcode, skipping")
        return

    outfile = PROPERTIES_DIR / f"{safe_filename(name)}.json"
    if outfile.exists():
        existing = json.loads(outfile.read_text(encoding="utf-8"))
        # Support both old (list) and new (dict) formats
        props = existing.get("properties", existing) if isinstance(existing, dict) else existing
        if props:
            print(f"  {name} — already scraped ({len(props)} properties)")
            return

    print(f"  {name} ({postcode})")

    try:
        await asyncio.sleep(REQUEST_DELAY)
        postcode_id = await resolve_postcode(page, postcode)
        if not postcode_id:
            print(f"    Could not resolve POSTCODE for {postcode}")
            outfile.write_text("[]", encoding="utf-8")
            return

        print(f"    {postcode_id}")
        search_url = rightmove_search_url(postcode_id, postcode)
        properties = await search_properties(page, postcode_id, postcode, MAX_PROPERTIES_PER_SCHOOL)

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

        output = {
            "rightmove_url": search_url,
            "properties": slim,
        }
        outfile.write_text(
            json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"    Saved {len(slim)} properties")

    except Exception as e:
        print(f"    Error: {e}")
        outfile.write_text(json.dumps({"rightmove_url": None, "properties": []}), encoding="utf-8")


async def main():
    print(f"Loading {GEOCODED_FILE}...")
    schools = json.loads(GEOCODED_FILE.read_text(encoding="utf-8"))

    filters = []
    if MIN_BEDROOMS is not None:
        filters.append(f"min {MIN_BEDROOMS} beds")
    if MAX_BEDROOMS is not None:
        filters.append(f"max {MAX_BEDROOMS} beds")
    if MIN_PRICE is not None:
        filters.append(f"min £{MIN_PRICE:,}")
    if MAX_PRICE is not None:
        filters.append(f"max £{MAX_PRICE:,}")
    filter_str = f" | Filters: {', '.join(filters)}" if filters else ""
    print(f"Searching Rightmove for {len(schools)} schools{filter_str}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        for school in schools:
            await scrape_school(page, school)

        await browser.close()

    print(f"\nDone. Results in {PROPERTIES_DIR}/")


if __name__ == "__main__":
    asyncio.run(main())

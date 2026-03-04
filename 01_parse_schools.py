#!/usr/bin/env python3
"""Fetch and parse top-100 comprehensive schools from Parent Power 2025."""

import json
import subprocess
from html.parser import HTMLParser

from config import (
    ALL_SCHOOLS_FILE,
    LONDON_SCHOOLS_FILE,
    LONDON_LOCATIONS,
)

PARENT_POWER_URL = (
    "https://dlv.tnl-parent-power.gcpp.io/2025"
    "?filterId=the-top-state-secondary-comprehensive-schools"
)


def fetch_html():
    """Fetch the Parent Power page via curl."""
    result = subprocess.run(
        [
            "curl", "-s", PARENT_POWER_URL,
            "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:148.0) Gecko/20100101 Firefox/148.0",
            "-H", "Accept: */*",
            "-H", "Accept-Language: en-US,en;q=0.9",
            "-H", "Accept-Encoding: gzip, deflate, br, zstd",
            "--compressed",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


class SchoolTableParser(HTMLParser):
    """Extract school data from the Parent Power HTML table.

    Each school occupies a <tbody> containing a data row with <td> cells:
      0: rank, 1: name, 2: location, 3: type,
      4: A-level %A*, 5: A-level %A*/A, 6: A-level %A*/B, 7: A-level rank,
      8: GCSE %9/8/7, 9: GCSE rank, 10: gender (via img alt attrs)
    """

    def __init__(self):
        super().__init__()
        self.schools = []
        self._in_data_row = False
        self._in_td = False
        self._cells = []
        self._current_text = ""
        self._gender_alts = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "") or ""

        if tag == "tr" and "pp-main-table-2023__table--row" in cls:
            self._in_data_row = True
            self._cells = []
            self._gender_alts = []

        if tag == "td" and self._in_data_row:
            self._in_td = True
            self._current_text = ""

        # Capture gender from img alt attributes inside the gender cell
        if tag == "img" and self._in_td and self._in_data_row:
            alt = attrs_dict.get("alt", "")
            if alt in ("Boys", "Girls", "Sixth form"):
                self._gender_alts.append(alt)

    def handle_data(self, data):
        if self._in_td:
            self._current_text += data

    def handle_endtag(self, tag):
        if tag == "td" and self._in_td:
            self._cells.append(self._current_text.strip())
            self._in_td = False

        if tag == "tr" and self._in_data_row:
            self._in_data_row = False
            if len(self._cells) >= 10:
                self._emit_school()

    def _emit_school(self):
        cells = self._cells
        # cell 0 = rank, cell 1 = name (from <a> text), etc.
        rank = cells[0].strip()
        name = cells[1].strip()
        location = cells[2].strip()
        school_type = cells[3].strip()

        school = {
            "rank": rank,
            "name": name,
            "location": location,
            "type": school_type,
            "alevel_pct_a_star": _parse_num(cells[4]),
            "alevel_pct_a_star_a": _parse_num(cells[5]),
            "alevel_pct_a_star_b": _parse_num(cells[6]),
            "alevel_rank": cells[7].strip() if len(cells) > 7 else None,
            "gcse_pct_7_9": _parse_num(cells[8]),
            "gcse_rank": cells[9].strip() if len(cells) > 9 else None,
            "gender": " ".join(self._gender_alts) if self._gender_alts else cells[10].strip() if len(cells) > 10 else None,
        }
        self.schools.append(school)


def _parse_num(value):
    """Convert a string to float, returning None for dashes or empty values."""
    value = value.strip() if value else ""
    if not value or value == "-":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_schools_from_html(html):
    """Parse school data from the Parent Power HTML page."""
    parser = SchoolTableParser()
    parser.feed(html)
    return parser.schools


def main():
    print("Fetching Parent Power 2025 data...")
    html = fetch_html()
    print(f"Fetched {len(html):,} bytes.")

    all_schools = parse_schools_from_html(html)
    print(f"Parsed {len(all_schools)} schools total.")

    # Save all schools
    ALL_SCHOOLS_FILE.write_text(
        json.dumps(all_schools, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {ALL_SCHOOLS_FILE}")

    # Filter to London
    london_schools = [s for s in all_schools if s["location"] in LONDON_LOCATIONS]
    print(f"Filtered to {len(london_schools)} Greater London schools:")
    for s in london_schools:
        print(f"  {s['rank']:>4}  {s['name']}  ({s['location']})")

    LONDON_SCHOOLS_FILE.write_text(
        json.dumps(london_schools, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {LONDON_SCHOOLS_FILE}")


if __name__ == "__main__":
    main()

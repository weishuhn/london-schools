"""Shared configuration for the London Schools Property Finder pipeline."""

from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
PROPERTIES_DIR = DATA_DIR / "properties"
INPUT_FILE = PROJECT_ROOT / "top-100-schools.txt"

ALL_SCHOOLS_FILE = DATA_DIR / "all_schools.json"
LONDON_SCHOOLS_FILE = DATA_DIR / "london_schools.json"
GEOCODED_FILE = DATA_DIR / "london_schools_geocoded.json"
NEIGHBOURHOODS_FILE = DATA_DIR / "neighbourhoods.json"
COMBINED_JSON = DATA_DIR / "combined_report.json"
COMBINED_CSV = DATA_DIR / "combined_report.csv"

# Ensure output dirs exist
DATA_DIR.mkdir(exist_ok=True)
PROPERTIES_DIR.mkdir(exist_ok=True)

# ── London filter ──────────────────────────────────────────────────────────────
# Locations that fall within Greater London
LONDON_LOCATIONS = {"London", "Harrow", "Barking", "Upminster"}

# ── Geocoding ──────────────────────────────────────────────────────────────────
NOMINATIM_USER_AGENT = "london-schools-finder/1.0"
GEOCODE_DELAY_SECONDS = 1.1  # Nominatim usage policy

# ── Rightmove / Scrapfly ──────────────────────────────────────────────────────
SCRAPFLY_KEY = "scp-live-09e995c269b7453bbb81451b2b4a1cab"
SEARCH_RADIUS_MILES = 0.5
MAX_PROPERTIES_PER_SCHOOL = 50

# ── Property filters (set to None to disable) ────────────────────────────────
MIN_BEDROOMS = 4  # e.g. 3
MAX_BEDROOMS = None  # e.g. 4
MIN_PRICE = 750_000  # e.g. 500_000
MAX_PRICE = 5_000_000  # e.g. 1_500_000

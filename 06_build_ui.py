#!/usr/bin/env python3
"""Build a self-contained HTML dashboard for London schools + properties."""

import json
from pathlib import Path

DATA_DIR = Path("data")
PROPERTIES_DIR = DATA_DIR / "properties"
OUTPUT = DATA_DIR / "london_schools.html"


def safe_filename(name):
    """Match the convention used by 04_rightmove_search.py."""
    return name.replace("/", "_").replace(" ", "_").replace("\u2019", "")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    # --- Load data ---
    schools = load_json(DATA_DIR / "london_schools_geocoded.json")
    neighbourhoods = load_json(DATA_DIR / "neighbourhoods.json")
    combined = load_json(DATA_DIR / "combined_report.json")

    # Build lookup from combined report
    combined_by_name = {s["name"]: s for s in combined}

    # Merge combined stats into school objects
    for s in schools:
        c = combined_by_name.get(s["name"], {})
        s["property_count"] = c.get("property_count", 0)
        s["avg_price"] = c.get("avg_price")
        s["min_price"] = c.get("min_price")
        s["max_price"] = c.get("max_price")
        s["neighbourhood_composite_score"] = c.get("neighbourhood_composite_score")
        s["neighbourhood_avg_gcse"] = c.get("neighbourhood_avg_gcse")
        s["neighbourhood_school_count"] = c.get("neighbourhood_school_count")
        s["rightmove_url"] = c.get("rightmove_url")

    # Load properties per school
    properties_by_school = {}
    total_props = 0
    for s in schools:
        fname = safe_filename(s["name"]) + ".json"
        pfile = PROPERTIES_DIR / fname
        if pfile.exists():
            raw = load_json(pfile)
            # Support both old (list) and new (dict with rightmove_url) formats
            if isinstance(raw, dict):
                props = raw.get("properties", [])
            else:
                props = raw
            properties_by_school[s["name"]] = props
            total_props += len(props)
        else:
            properties_by_school[s["name"]] = []
            print(f"  Warning: no property file for {s['name']} ({fname})")

    # Borough name mapping (our data -> GeoJSON names)
    borough_map = {
        "Barking": "Barking and Dagenham",
        "London Borough of Barnet": "Barnet",
        "London Borough of Brent": "Brent",
        "London Borough of Camden": "Camden",
        "London Borough of Ealing": "Ealing",
        "London Borough of Hackney": "Hackney",
        "London Borough of Hammersmith and Fulham": "Hammersmith and Fulham",
        "London Borough of Haringey": "Haringey",
        "London Borough of Harrow": "Harrow",
        "London Borough of Havering": "Havering",
        "London Borough of Merton": "Merton",
        "London Borough of Richmond upon Thames": "Richmond upon Thames",
        "London Borough of Southwark": "Southwark",
        "London Borough of Sutton": "Sutton",
        "London Borough of Wandsworth": "Wandsworth",
        "Marylebone": "Westminster",
        "Millbank": "Westminster",
        "Royal Borough of Kensington and Chelsea": "Kensington and Chelsea",
    }

    # Load stations
    stations_file = DATA_DIR / "london_stations.json"
    stations = load_json(stations_file) if stations_file.exists() else []

    # Load transport lines GeoJSON
    lines_file = DATA_DIR / "london_lines.json"
    lines_geojson = load_json(lines_file) if lines_file.exists() else {"type": "FeatureCollection", "features": []}

    print(f"Loaded {len(schools)} schools, {len(neighbourhoods)} neighbourhoods, {total_props} properties, {len(stations)} stations, {len(lines_geojson.get('features', []))} transport lines")

    # --- Build HTML ---
    schools_json = json.dumps(schools, ensure_ascii=False)
    neighbourhoods_json = json.dumps(neighbourhoods, ensure_ascii=False)
    properties_json = json.dumps(properties_by_school, ensure_ascii=False)
    borough_map_json = json.dumps(borough_map, ensure_ascii=False)
    stations_json = json.dumps(stations, ensure_ascii=False)
    lines_json = json.dumps(lines_geojson, ensure_ascii=False)

    html = build_html(schools_json, neighbourhoods_json, properties_json, borough_map_json, stations_json, lines_json)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Written to {OUTPUT} ({len(html):,} bytes)")


def build_html(schools_json, neighbourhoods_json, properties_json, borough_map_json, stations_json, lines_json):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>London Schools Property Finder</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Oxygen,Ubuntu,sans-serif; background:#0f172a; color:#e2e8f0; }}

/* Tabs */
.tab-bar {{ display:flex; background:#1e293b; border-bottom:2px solid #334155; }}
.tab-btn {{ padding:12px 24px; cursor:pointer; border:none; background:none; color:#94a3b8; font-size:14px; font-weight:600; transition:all .2s; }}
.tab-btn:hover {{ color:#e2e8f0; background:#334155; }}
.tab-btn.active {{ color:#38bdf8; border-bottom:2px solid #38bdf8; margin-bottom:-2px; }}
.tab-page {{ display:none; height:calc(100vh - 46px); }}
.tab-page.active {{ display:flex; }}

/* Page 1: Schools Map */
.sidebar {{ width:320px; min-width:320px; background:#1e293b; overflow-y:auto; border-right:1px solid #334155; }}
.sidebar-header {{ padding:16px; border-bottom:1px solid #334155; }}
.sidebar-header h2 {{ font-size:16px; color:#f1f5f9; margin-bottom:8px; }}
.search-box {{ width:100%; padding:8px 12px; border:1px solid #475569; border-radius:6px; background:#0f172a; color:#e2e8f0; font-size:13px; }}
.search-box::placeholder {{ color:#64748b; }}
.borough-group {{ border-bottom:1px solid #334155; }}
.borough-title {{ padding:10px 16px; font-size:12px; font-weight:700; color:#94a3b8; text-transform:uppercase; letter-spacing:.5px; background:#1a2332; cursor:pointer; }}
.borough-title:hover {{ background:#253347; }}
.school-item {{ padding:10px 16px; cursor:pointer; display:flex; align-items:center; gap:10px; transition:background .15s; border-bottom:1px solid #1a2332; }}
.school-item:hover {{ background:#334155; }}
.rank-badge {{ min-width:28px; height:28px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:700; color:#fff; }}
.school-info {{ flex:1; min-width:0; }}
.school-name {{ font-size:13px; font-weight:600; color:#f1f5f9; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.school-meta {{ font-size:11px; color:#94a3b8; margin-top:2px; }}
#main-map {{ flex:1; }}

/* Page 2: Properties */
.props-panel {{ width:320px; min-width:320px; background:#1e293b; overflow-y:auto; border-right:1px solid #334155; padding:16px; }}
.props-panel h2 {{ font-size:16px; color:#f1f5f9; margin-bottom:12px; }}
.props-panel label {{ display:block; font-size:12px; color:#94a3b8; margin-bottom:4px; margin-top:12px; }}
.props-panel select, .props-panel input[type=number] {{ width:100%; padding:8px 10px; border:1px solid #475569; border-radius:6px; background:#0f172a; color:#e2e8f0; font-size:13px; }}
.school-card {{ background:#0f172a; border:1px solid #334155; border-radius:8px; padding:14px; margin-top:14px; }}
.school-card h3 {{ font-size:14px; color:#f1f5f9; margin-bottom:8px; }}
.school-card .stat {{ display:flex; justify-content:space-between; font-size:12px; padding:3px 0; }}
.school-card .stat-label {{ color:#94a3b8; }}
.school-card .stat-value {{ color:#e2e8f0; font-weight:600; }}
.filter-section {{ margin-top:16px; padding-top:16px; border-top:1px solid #334155; }}
.result-count {{ margin-top:12px; font-size:13px; color:#38bdf8; font-weight:600; }}

.props-right {{ flex:1; display:flex; flex-direction:column; }}
#props-map {{ height:40%; min-height:250px; }}
.props-list {{ flex:1; overflow-y:auto; padding:16px; background:#0f172a; }}
.prop-card {{ background:#1e293b; border:1px solid #334155; border-radius:8px; overflow:hidden; margin-bottom:12px; transition:border-color .15s; display:flex; }}
.prop-card:hover {{ border-color:#38bdf8; }}
.prop-thumb {{ width:140px; min-width:140px; height:140px; object-fit:cover; background:#0f172a; }}
.prop-body {{ padding:14px; flex:1; min-width:0; }}
.prop-price {{ font-size:18px; font-weight:700; color:#f1f5f9; }}
.prop-distance {{ font-size:12px; color:#38bdf8; margin-left:8px; }}
.prop-address {{ font-size:13px; color:#94a3b8; margin-top:4px; }}
.prop-details {{ display:flex; gap:12px; margin-top:8px; font-size:12px; color:#cbd5e1; }}
.prop-summary {{ font-size:12px; color:#64748b; margin-top:6px; line-height:1.4; }}
.prop-link {{ display:inline-block; margin-top:8px; font-size:12px; color:#38bdf8; text-decoration:none; }}
.prop-link:hover {{ text-decoration:underline; }}
.no-results {{ text-align:center; padding:40px; color:#64748b; }}

/* Scrollbar */
::-webkit-scrollbar {{ width:6px; }}
::-webkit-scrollbar-track {{ background:#0f172a; }}
::-webkit-scrollbar-thumb {{ background:#475569; border-radius:3px; }}

/* Leaflet popup */
.leaflet-popup-content-wrapper {{ background:#1e293b; color:#e2e8f0; border-radius:8px; }}
.leaflet-popup-tip {{ background:#1e293b; }}
.leaflet-popup-content {{ font-size:13px; line-height:1.5; }}
.leaflet-popup-content a {{ color:#38bdf8; }}
.station-icon {{ filter: drop-shadow(0 1px 2px rgba(0,0,0,.5)); }}
.popup-title {{ font-weight:700; font-size:14px; margin-bottom:6px; }}
.popup-stat {{ font-size:12px; color:#94a3b8; }}

/* Mobile filter toggle – hidden on desktop */
.mobile-filter-toggle {{ display:none; }}

/* --- Mobile responsive --- */
@media (max-width: 768px) {{
  /* Tab bar */
  .tab-btn {{ flex:1; text-align:center; padding:10px 8px; font-size:13px; }}

  /* Page 1: Schools Map */
  .tab-page.active {{ flex-direction:column; }}
  .sidebar {{ width:100%; min-width:unset; max-height:40vh; border-right:none; border-bottom:1px solid #334155; }}
  #main-map {{ flex:1; min-height:0; }}

  /* Page 2: Properties */
  .props-panel {{ width:100%; min-width:unset; max-height:none; overflow:visible; border-right:none; border-bottom:1px solid #334155; }}
  .props-panel .filter-section,
  .props-panel #school-detail-card {{ display:none; }}
  .props-panel.filters-open .filter-section,
  .props-panel.filters-open #school-detail-card {{ display:block; }}
  .props-right {{ flex:1; min-height:0; }}
  #props-map {{ height:250px; min-height:200px; }}
  .props-list {{ flex:1; overflow-y:auto; }}

  /* Property cards */
  .prop-card {{ flex-direction:column; }}
  .prop-thumb {{ width:100%; min-width:unset; height:180px; }}

  /* Mobile filter toggle */
  .mobile-filter-toggle {{ display:block; width:100%; margin-top:8px; padding:8px; border:1px solid #475569; border-radius:6px; background:#0f172a; color:#94a3b8; font-size:13px; cursor:pointer; }}
}}
</style>
</head>
<body>

<div class="tab-bar">
  <button class="tab-btn active" data-tab="page-schools">Schools Map</button>
  <button class="tab-btn" data-tab="page-properties">School Properties</button>
</div>

<div id="page-schools" class="tab-page active">
  <div class="sidebar">
    <div class="sidebar-header">
      <h2>London Top Schools</h2>
      <input type="text" class="search-box" id="school-search" placeholder="Search schools...">
    </div>
    <div id="school-list"></div>
  </div>
  <div id="main-map"></div>
</div>

<div id="page-properties" class="tab-page">
  <div class="props-panel">
    <h2>School Properties</h2>
    <label for="school-select">Select School</label>
    <select id="school-select"></select>
    <button class="mobile-filter-toggle" id="mobile-filter-toggle">Show Filters &amp; Details</button>
    <div id="school-detail-card"></div>
    <div class="filter-section">
      <label for="filter-min-price">Min Price (&pound;)</label>
      <input type="number" id="filter-min-price" placeholder="e.g. 750000" step="50000">
      <label for="filter-max-price">Max Price (&pound;)</label>
      <input type="number" id="filter-max-price" placeholder="e.g. 5000000" step="50000">
      <label for="filter-beds">Min Bedrooms</label>
      <select id="filter-beds">
        <option value="0">Any</option>
        <option value="3">3</option>
        <option value="4">4</option>
        <option value="5">5</option>
        <option value="6">6+</option>
      </select>
      <label for="filter-type">Property Type</label>
      <select id="filter-type">
        <option value="">All</option>
        <option value="Flat">Flat</option>
        <option value="Terraced">Terraced</option>
        <option value="Semi-Detached">Semi-Detached</option>
        <option value="Detached">Detached</option>
        <option value="End of Terrace">End of Terrace</option>
      </select>
      <div class="result-count" id="result-count"></div>
    </div>
  </div>
  <div class="props-right">
    <div id="props-map"></div>
    <div class="props-list" id="props-list"></div>
  </div>
</div>

<script>
const SCHOOLS = {schools_json};
const NEIGHBOURHOODS = {neighbourhoods_json};
const PROPERTIES = {properties_json};
const BOROUGH_MAP = {borough_map_json};
const STATIONS = {stations_json};
const LINES = {lines_json};

const MODE_COLORS = {{
  'tube': '#000000',
  'dlr': '#00A4A7',
  'overground': '#EE7C0E',
  'elizabeth-line': '#6950A1',
  'tram': '#84B817',
  'national-rail': '#E21836'
}};

let mainMap, propsMap, mainMarkers = {{}}, propsMarkers = [];
let propsLineLayer = null;
let mainTransitMarkers = [];
let mainLineLayer = null;
let currentSchool = null;

function stationIcon(modes, lines) {{
  const primaryMode = modes.length > 0 ? modes[0] : '';
  let color = MODE_COLORS[primaryMode] || '#000';
  if (primaryMode === 'tube' && lines.length > 0) {{
    const lineFeature = LINES.features && LINES.features.find(f => f.properties.id === lines[0]);
    if (lineFeature) color = lineFeature.properties.color;
  }}
  let svg;
  if (primaryMode === 'tram') {{
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" width="20" height="20">'
      + '<line x1="10" y1="1" x2="10" y2="4" stroke="' + color + '" stroke-width="2"/>'
      + '<line x1="6" y1="1" x2="14" y2="1" stroke="' + color + '" stroke-width="1.5"/>'
      + '<rect x="4" y="4" width="12" height="10" rx="3" fill="' + color + '"/>'
      + '<rect x="6" y="6" width="3" height="4" rx="1" fill="#fff"/>'
      + '<rect x="11" y="6" width="3" height="4" rx="1" fill="#fff"/>'
      + '<circle cx="7" cy="17" r="1.5" fill="' + color + '"/>'
      + '<circle cx="13" cy="17" r="1.5" fill="' + color + '"/>'
      + '<line x1="4" y1="19" x2="16" y2="19" stroke="#666" stroke-width="1.5"/>'
      + '</svg>';
  }} else if (primaryMode === 'national-rail') {{
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" width="20" height="20">'
      + '<rect x="4" y="3" width="12" height="11" rx="3" ry="3" fill="' + color + '"/>'
      + '<rect x="3" y="2" width="14" height="3" rx="1.5" fill="' + color + '"/>'
      + '<rect x="6" y="6" width="3" height="3" rx="1" fill="#fff"/>'
      + '<rect x="11" y="6" width="3" height="3" rx="1" fill="#fff"/>'
      + '<circle cx="5" cy="12" r="0.8" fill="#ff0"/>'
      + '<circle cx="15" cy="12" r="0.8" fill="#ff0"/>'
      + '<rect x="5" y="14" width="2" height="3" fill="#555"/>'
      + '<rect x="13" y="14" width="2" height="3" fill="#555"/>'
      + '<circle cx="7" cy="17.5" r="1.5" fill="#333"/>'
      + '<circle cx="13" cy="17.5" r="1.5" fill="#333"/>'
      + '<line x1="3" y1="19" x2="17" y2="19" stroke="#666" stroke-width="1.5"/>'
      + '</svg>';
  }} else {{
    // Roundel for tube, dlr, overground, elizabeth-line, and default
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" width="20" height="20">'
      + '<circle cx="10" cy="10" r="8" stroke="' + color + '" stroke-width="3" fill="none"/>'
      + '<rect x="2" y="7.5" width="16" height="5" rx="1" fill="' + color + '"/>'
      + '</svg>';
  }}
  return L.divIcon({{
    className: 'station-icon',
    html: svg,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
    popupAnchor: [0, -10]
  }});
}}

// --- Utilities ---
function haversineMiles(lat1, lon1, lat2, lon2) {{
  const R = 3958.8;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}}

function formatPrice(n) {{
  if (n == null) return 'N/A';
  return '\\u00a3' + n.toLocaleString('en-GB');
}}

// Rank-based green→yellow→red gradient
const RANK_MIN = Math.min(...SCHOOLS.map(s => parseInt(s.rank) || 999));
const RANK_MAX = Math.max(...SCHOOLS.map(s => parseInt(s.rank) || 0));

function rankColor(rank) {{
  const r = parseInt(rank) || 50;
  const t = Math.max(0, Math.min(1, (r - RANK_MIN) / (RANK_MAX - RANK_MIN)));
  // green(76,175,80) → yellow(255,235,59) → red(244,67,54)
  let red, green, blue;
  if (t < 0.5) {{
    const u = t * 2;
    red = Math.round(76 + (255 - 76) * u);
    green = Math.round(175 + (235 - 175) * u);
    blue = Math.round(80 + (59 - 80) * u);
  }} else {{
    const u = (t - 0.5) * 2;
    red = Math.round(255 + (244 - 255) * u);
    green = Math.round(235 + (67 - 235) * u);
    blue = Math.round(59 + (54 - 59) * u);
  }}
  return `rgb(${{red}},${{green}},${{blue}})`;
}}

function shortBorough(b) {{
  return b.replace('London Borough of ', '').replace('Royal Borough of ', '');
}}

// --- Tab switching ---
function initTabs() {{
  document.querySelectorAll('.tab-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-page').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(btn.dataset.tab).classList.add('active');
      setTimeout(() => {{
        if (mainMap) mainMap.invalidateSize();
        if (propsMap) propsMap.invalidateSize();
        if (btn.dataset.tab === 'page-properties') {{
          if (!propsMap) {{
            initPropsMap();
          }}
          if (!currentSchool) {{
            const select = document.getElementById('school-select');
            if (select.options.length > 0) {{
              select.selectedIndex = 0;
              renderSchoolProperties(select.value);
            }}
          }}
        }}
      }}, 100);
    }});
  }});
}}

// --- Page 1: Schools Map ---
function initMainMap() {{
  mainMap = L.map('main-map').setView([51.509, -0.118], 11);
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 18
  }}).addTo(mainMap);

  SCHOOLS.forEach(s => {{
    const color = rankColor(s.rank);
    const marker = L.circleMarker([s.lat, s.lon], {{
      radius: 8, fillColor: color, color: '#fff', weight: 2, fillOpacity: 0.9
    }}).addTo(mainMap);

    const propCount = s.property_count || 0;
    marker.bindPopup(`
      <div class="popup-title">${{s.name}}</div>
      <div class="popup-stat">Rank: #${{s.rank}} &bull; GCSE 7-9: ${{s.gcse_pct_7_9}}%</div>
      <div class="popup-stat">A-level A*-B: ${{s.alevel_pct_a_star_b}}%</div>
      <div class="popup-stat">Borough: ${{shortBorough(s.borough)}}</div>
      <div class="popup-stat">Postcode: ${{s.postcode}}</div>
      <div class="popup-stat">Properties: ${{propCount}}</div>
      ${{propCount > 0 ? '<a href="#" onclick="switchToProperties(\\'' + s.name.replace(/'/g, "\\\\'") + '\\');return false;" style="color:#38bdf8;font-size:12px;">View Properties &rarr;</a>' : ''}}
    `);
    mainMarkers[s.name] = marker;
  }});

  // Load borough outlines
  fetch('https://raw.githubusercontent.com/radoi90/housequest-data/master/london_boroughs.geojson')
    .then(r => r.json())
    .then(geo => {{
      const ourBoroughs = new Set(Object.values(BOROUGH_MAP));
      L.geoJSON(geo, {{
        filter: feature => ourBoroughs.has(feature.properties.name),
        style: {{ color: '#d97706', weight: 2, dashArray: '6 4', fillOpacity: 0.03, fillColor: '#d97706' }},
        interactive: false
      }}).addTo(mainMap);
    }})
    .catch(() => console.log('Borough GeoJSON unavailable'));
}}

function renderSidebar() {{
  // Group by borough, sort by neighbourhood composite score
  const byBorough = {{}};
  SCHOOLS.forEach(s => {{
    const b = s.borough;
    if (!byBorough[b]) byBorough[b] = [];
    byBorough[b].push(s);
  }});

  // Sort boroughs by best composite score
  const boroughKeys = Object.keys(byBorough).sort((a, b) => {{
    const scoreA = Math.max(...byBorough[a].map(s => s.neighbourhood_composite_score || 0));
    const scoreB = Math.max(...byBorough[b].map(s => s.neighbourhood_composite_score || 0));
    return scoreB - scoreA;
  }});

  const container = document.getElementById('school-list');
  let html = '';
  boroughKeys.forEach(borough => {{
    const schools = byBorough[borough].sort((a, b) => (parseInt(a.rank) || 999) - (parseInt(b.rank) || 999));
    html += `<div class="borough-group" data-borough="${{borough}}">`;
    html += `<div class="borough-title">${{shortBorough(borough)}} (${{schools.length}})</div>`;
    schools.forEach(s => {{
      html += `<div class="school-item" data-name="${{s.name.replace(/"/g, '&quot;')}}">
        <div class="rank-badge" style="background:${{rankColor(s.rank)}}">#${{s.rank}}</div>
        <div class="school-info">
          <div class="school-name">${{s.name}}</div>
          <div class="school-meta">GCSE 7-9: ${{s.gcse_pct_7_9}}% &bull; ${{s.property_count || 0}} properties</div>
        </div>
      </div>`;
    }});
    html += `</div>`;
  }});
  container.innerHTML = html;

  // Click to pan
  container.querySelectorAll('.school-item').forEach(el => {{
    el.addEventListener('click', () => panToSchool(el.dataset.name));
  }});

  // Search filter
  document.getElementById('school-search').addEventListener('input', e => {{
    const q = e.target.value.toLowerCase();
    container.querySelectorAll('.school-item').forEach(el => {{
      el.style.display = el.dataset.name.toLowerCase().includes(q) ? '' : 'none';
    }});
    container.querySelectorAll('.borough-group').forEach(g => {{
      const visible = g.querySelectorAll('.school-item:not([style*="display: none"])');
      g.style.display = visible.length ? '' : 'none';
    }});
  }});
}}

function panToSchool(name) {{
  const marker = mainMarkers[name];
  if (marker) {{
    mainMap.setView(marker.getLatLng(), 14);
    marker.openPopup();
  }}
  showMainTransit(name);
}}

function showMainTransit(name) {{
  // Clear previous transit overlay
  mainTransitMarkers.forEach(m => mainMap.removeLayer(m));
  mainTransitMarkers = [];
  if (mainLineLayer) {{ mainMap.removeLayer(mainLineLayer); mainLineLayer = null; }}

  const school = SCHOOLS.find(s => s.name === name);
  if (!school) return;

  // Find nearby line IDs
  const nearbyLineIds = new Set();
  STATIONS.forEach(st => {{
    const d = haversineMiles(school.lat, school.lon, st.lat, st.lon);
    if (d <= 1.5) {{
      (st.lines || []).forEach(lid => nearbyLineIds.add(lid));
    }}
  }});

  // Draw lines
  if (LINES.features && LINES.features.length > 0) {{
    const filtered = {{
      type: 'FeatureCollection',
      features: LINES.features.filter(f => nearbyLineIds.has(f.properties.id))
    }};
    mainLineLayer = L.geoJSON(filtered, {{
      style: function(feature) {{
        return {{ color: feature.properties.color || '#888', weight: 3, opacity: 0.6 }};
      }}
    }}).addTo(mainMap);
    mainLineLayer.bringToBack();
  }}

  // Draw station markers
  STATIONS.forEach(st => {{
    const d = haversineMiles(school.lat, school.lon, st.lat, st.lon);
    if (d <= 1.5) {{
      const modes = st.modes || [];
      const lines = st.lines || [];
      const m = L.marker([st.lat, st.lon], {{ icon: stationIcon(modes, lines) }}).addTo(mainMap);
      const modeStr = modes.join(', ');
      const lineStr = lines.join(', ');
      m.bindPopup(`<b>${{st.name}}</b><br>Mode: ${{modeStr}}<br>Lines: ${{lineStr}}<br>${{d.toFixed(2)}} mi from school`);
      mainTransitMarkers.push(m);
    }}
  }});
}}

// --- Page 2: Properties ---
function initPropsPage() {{
  // Populate dropdown sorted by rank
  const select = document.getElementById('school-select');
  const sorted = [...SCHOOLS].sort((a, b) => (parseInt(a.rank) || 999) - (parseInt(b.rank) || 999));
  sorted.forEach(s => {{
    const opt = document.createElement('option');
    opt.value = s.name;
    opt.textContent = `#${{s.rank}} ${{s.name}}`;
    select.appendChild(opt);
  }});

  select.addEventListener('change', () => renderSchoolProperties(select.value));

  // Mobile filter toggle
  document.getElementById('mobile-filter-toggle').addEventListener('click', function() {{
    const panel = document.querySelector('.props-panel');
    panel.classList.toggle('filters-open');
    this.textContent = panel.classList.contains('filters-open') ? 'Hide Filters & Details' : 'Show Filters & Details';
    setTimeout(() => {{ if (propsMap) propsMap.invalidateSize(); }}, 100);
  }});

  // Filter listeners
  ['filter-min-price','filter-max-price','filter-beds','filter-type'].forEach(id => {{
    document.getElementById(id).addEventListener('change', () => {{
      if (currentSchool) renderSchoolProperties(currentSchool);
    }});
  }});

  // Handle hash navigation
  if (window.location.hash) {{
    const name = decodeURIComponent(window.location.hash.slice(1));
    const match = SCHOOLS.find(s => s.name === name);
    if (match) {{
      document.querySelectorAll('.tab-btn')[1].click();
      select.value = match.name;
      renderSchoolProperties(match.name);
    }}
  }}
}}

function initPropsMap() {{
  propsMap = L.map('props-map').setView([51.509, -0.118], 13);
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 18
  }}).addTo(propsMap);
}}

function switchToProperties(name) {{
  document.querySelectorAll('.tab-btn')[1].click();
  document.getElementById('school-select').value = name;
  window.location.hash = encodeURIComponent(name);
  // Delay render to let tab become visible and map init
  setTimeout(() => {{
    if (!propsMap) initPropsMap();
    renderSchoolProperties(name);
  }}, 100);
}}

function applyPropertyFilters(props) {{
  const minPrice = parseInt(document.getElementById('filter-min-price').value) || 0;
  const maxPrice = parseInt(document.getElementById('filter-max-price').value) || Infinity;
  const minBeds = parseInt(document.getElementById('filter-beds').value) || 0;
  const propType = document.getElementById('filter-type').value;

  return props.filter(p => {{
    if (p.price < minPrice || p.price > maxPrice) return false;
    if (p.bedrooms < minBeds) return false;
    if (propType && p.property_type !== propType) return false;
    return true;
  }});
}}

function renderSchoolProperties(name) {{
  currentSchool = name;
  const school = SCHOOLS.find(s => s.name === name);
  if (!school) return;

  // Ensure map exists
  if (!propsMap) initPropsMap();

  // School detail card
  const card = document.getElementById('school-detail-card');
  card.innerHTML = `<div class="school-card">
    <h3>${{school.name}}</h3>
    <div class="stat"><span class="stat-label">Rank</span><span class="stat-value">#${{school.rank}}</span></div>
    <div class="stat"><span class="stat-label">Borough</span><span class="stat-value">${{shortBorough(school.borough)}}</span></div>
    <div class="stat"><span class="stat-label">Postcode</span><span class="stat-value">${{school.postcode}}</span></div>
    <div class="stat"><span class="stat-label">GCSE 7-9</span><span class="stat-value">${{school.gcse_pct_7_9}}%</span></div>
    <div class="stat"><span class="stat-label">A-level A*-B</span><span class="stat-value">${{school.alevel_pct_a_star_b}}%</span></div>
    <div class="stat"><span class="stat-label">Type</span><span class="stat-value">${{school.type}}</span></div>
    <div class="stat"><span class="stat-label">Gender</span><span class="stat-value">${{school.gender}}</span></div>
    <div class="stat"><span class="stat-label">Properties</span><span class="stat-value">${{school.property_count || 0}}</span></div>
    ${{school.rightmove_url ? '<a href="' + school.rightmove_url + '" target="_blank" rel="noopener" style="display:block;margin-top:8px;text-align:center;color:#38bdf8;font-size:13px;">View all on Rightmove &rarr;</a>' : ''}}
  </div>`;

  // Get and filter properties
  let props = (PROPERTIES[name] || []).map(p => ({{
    ...p,
    distance: haversineMiles(school.lat, school.lon, p.latitude, p.longitude)
  }}));
  props = applyPropertyFilters(props);
  props.sort((a, b) => a.distance - b.distance);

  document.getElementById('result-count').textContent = `${{props.length}} properties found`;

  // Update map
  propsMarkers.forEach(m => propsMap.removeLayer(m));
  propsMarkers = [];

  const schoolMarker = L.marker([school.lat, school.lon], {{
    icon: L.divIcon({{
      className: '',
      html: '<div style="background:#dc2626;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;white-space:nowrap;border:2px solid #fff;box-shadow:0 2px 4px rgba(0,0,0,.3);">' + school.name.split(' ').slice(0,3).join(' ') + '</div>',
      iconAnchor: [40, 20]
    }})
  }}).addTo(propsMap);
  propsMarkers.push(schoolMarker);

  const bounds = L.latLngBounds([[school.lat, school.lon]]);
  props.forEach(p => {{
    const m = L.circleMarker([p.latitude, p.longitude], {{
      radius: 6, fillColor: '#2563eb', color: '#fff', weight: 1.5, fillOpacity: 0.8
    }}).addTo(propsMap);
    const popupImg = p.image_url ? `<img src="${{p.image_url}}" style="width:100%;max-width:200px;border-radius:4px;margin-bottom:6px;" loading="lazy">` : '';
    m.bindPopup(`${{popupImg}}<b>${{p.price_display}}</b><br>${{p.address.replace(/\\n/g, ', ')}}<br>${{p.bedrooms}} bed &bull; ${{p.property_type}}<br><a href="${{p.url}}" target="_blank" rel="noopener" style="color:#38bdf8;">View on Rightmove &rarr;</a>`);
    propsMarkers.push(m);
    bounds.extend([p.latitude, p.longitude]);
  }});

  // Add transport lines (filtered to lines with at least one station within 1.5mi)
  if (propsLineLayer) {{
    propsMap.removeLayer(propsLineLayer);
    propsLineLayer = null;
  }}
  const nearbyStations = new Set();
  const nearbyLineIds = new Set();
  STATIONS.forEach(st => {{
    const d = haversineMiles(school.lat, school.lon, st.lat, st.lon);
    if (d <= 1.5) {{
      nearbyStations.add(st.name);
      (st.lines || []).forEach(lid => nearbyLineIds.add(lid));
    }}
  }});
  if (LINES.features && LINES.features.length > 0) {{
    const filtered = {{
      type: 'FeatureCollection',
      features: LINES.features.filter(f => nearbyLineIds.has(f.properties.id))
    }};
    propsLineLayer = L.geoJSON(filtered, {{
      style: function(feature) {{
        return {{
          color: feature.properties.color || '#888',
          weight: 3,
          opacity: 0.6
        }};
      }}
    }}).addTo(propsMap);
    // Ensure lines render behind markers
    propsLineLayer.bringToBack();
  }}

  // Add nearby stations (within ~1.5 miles) with mode-colored markers
  STATIONS.forEach(st => {{
    const d = haversineMiles(school.lat, school.lon, st.lat, st.lon);
    if (d <= 1.5) {{
      const modes = st.modes || [];
      const lines = st.lines || [];
      const m = L.marker([st.lat, st.lon], {{ icon: stationIcon(modes, lines) }}).addTo(propsMap);
      const modeStr = modes.join(', ');
      const lineStr = lines.join(', ');
      m.bindPopup(`<b>${{st.name}}</b><br>Mode: ${{modeStr}}<br>Lines: ${{lineStr}}<br>${{d.toFixed(2)}} mi from school`);
      propsMarkers.push(m);
      bounds.extend([st.lat, st.lon]);
    }}
  }});

  if (props.length > 0) {{
    propsMap.fitBounds(bounds.pad(0.1));
  }} else {{
    propsMap.setView([school.lat, school.lon], 14);
  }}

  // Render property cards
  const list = document.getElementById('props-list');
  if (props.length === 0) {{
    list.innerHTML = '<div class="no-results">No properties match the current filters.</div>';
    return;
  }}

  list.innerHTML = props.map(p => `
    <div class="prop-card">
      ${{p.image_url ? '<img class="prop-thumb" src="' + p.image_url + '" loading="lazy" alt="">' : ''}}
      <div class="prop-body">
        <span class="prop-price">${{p.price_display}}</span>
        <span class="prop-distance">${{p.distance.toFixed(2)}} mi</span>
        <div class="prop-address">${{p.address.replace(/\\n/g, ', ')}}</div>
        <div class="prop-details">
          <span>${{p.bedrooms}} bed</span>
          <span>${{p.bathrooms}} bath</span>
          <span>${{p.property_type}}</span>
        </div>
        ${{p.summary ? '<div class="prop-summary">' + p.summary.slice(0, 150) + (p.summary.length > 150 ? '...' : '') + '</div>' : ''}}
        <a class="prop-link" href="${{p.url}}" target="_blank" rel="noopener">View on Rightmove &rarr;</a>
      </div>
    </div>
  `).join('');
  list.scrollTop = 0;
}}

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {{
  initTabs();
  initMainMap();
  renderSidebar();
  initPropsPage();
}});
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()

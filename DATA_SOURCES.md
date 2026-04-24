# DATA_SOURCES.md — Data Sources Reference

Every dataset used in this project is documented here. For each source:
where to get it, what format it comes in, which fields to keep, and known issues.

---

## Dataset 1: Census Tract Boundaries (Cook County)

**What it is**: Geographic boundaries of all census tracts in Cook County,
Illinois. Chicago lies entirely within Cook County. The tracts are clipped
to the Chicago city boundary in Stage 2.

**Source**: US Census Bureau — TIGER/Line via pygris

**Code**:
```python
import pygris
tracts = pygris.tracts(state="17", county="031", year=2020)
```

**Alternative (REST API)**:
```
https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2020/MapServer/8/query
where=STATE='17' AND COUNTY='031'
outFields=GEOID,NAME,AREALAND,AREAWATER
returnGeometry=true
outSR=4326
f=geojson
```

**Output format**: GeoJSON, EPSG:4326
**Fields to keep**:
| Field | Type | Description |
|---|---|---|
| `GEOID` | string | 11-digit FIPS: state(2) + county(3) + tract(6) |
| `NAME` | string | Human-readable tract name |
| `AREALAND` | float | Land area in square metres |
| `geometry` | Polygon | Tract boundary |

**Expected row count**: ~1,300 Cook County tracts
**After Chicago clip**: ~800 tracts

**Known issues**:
- Some tracts in Cook County overlap the Chicago city boundary. The clip
  operation in Stage 2 may produce slivers for edge tracts. These are fine
  to keep — the gap score will reflect their actual (partial) area.
- GEOID format from TIGER: `"17031010100"` (11 digits, no prefix)
- Match carefully against the population join key from the ACS API

---

## Dataset 2: Total Population by Tract

**What it is**: Total population per census tract from the American Community
Survey (ACS) 5-year estimates. Used as the weight in the gap score formula.

**Source**: US Census Bureau — ACS Data API

**API URL**:
```
https://api.census.gov/data/2022/acs/acs5
```

**Query**:
```
get=B01003_001E,GEO_ID
for=tract:*
in=state:17 county:031
```

**Full example URL**:
```
https://api.census.gov/data/2022/acs/acs5?get=B01003_001E,GEO_ID&for=tract:*&in=state:17%20county:031
```

**Response format**:
```json
[
  ["B01003_001E", "GEO_ID", "state", "county", "tract"],
  ["3254", "1400000US17031010100", "17", "031", "010100"],
  ...
]
```

**Fields**:
| Field | Rename to | Type | Notes |
|---|---|---|---|
| `B01003_001E` | `population` | int | Total population |
| `GEO_ID` | — | string | Format: `"1400000US17031010100"` |

**Null sentinel**: Replace `-666666666` with `0` (tracts with 0 population
are typically parks, airports, or industrial areas — they get a gap score of 0)

**Join key construction**:
```python
population_df["GEOID"] = population_df["GEO_ID"].str[-11:]
# "1400000US17031010100" → "17031010100"
```

**Expected row count**: ~1,300 rows
**Expected Chicago population**: ~2.7 million total

---

## Dataset 3: Urgent Care / Health Facilities

**What it is**: Locations of existing urgent care clinics and health facilities
in Chicago. Used as the origin points for isochrone generation.

**Source**: Chicago Data Portal — Socrata REST API

**Primary endpoint**:
```
https://data.cityofchicago.org/resource/iqnk-2tcu.json
```
This is the "Public Health Facilities" dataset.

**Query parameters**:
```
$limit=5000
$where=facility_type like '%URGENT%' OR facility_type like '%CLINIC%'
```

**Full URL**:
```
https://data.cityofchicago.org/resource/iqnk-2tcu.json?$limit=5000
```

**Fallback endpoint** (if primary returns insufficient results):
```
https://data.cityofchicago.org/resource/f5ex-mxwn.json
```
This is the "Health and Human Services" facilities dataset.

**Third fallback**: Search the Chicago Data Portal directly
at `data.cityofchicago.org` for "urgent care" or "health facilities" and
use the GeoJSON export link from the dataset page.

**Response format**: JSON array of objects
**Fields to extract**:
| Field | Type | Notes |
|---|---|---|
| `facility_name` or `name` | string | Clinic name |
| `address` | string | Street address |
| `facility_type` | string | Type classification |
| `longitude` | float | WGS84 longitude |
| `latitude` | float | WGS84 latitude |

**GeoDataFrame creation**:
```python
gdf = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df["longitude"].astype(float),
                                 df["latitude"].astype(float)),
    crs="EPSG:4326"
)
```

**Expected count before clip**: 50–300 facilities
**Expected count after Chicago clip**: 50–200 facilities

**Known issues**:
- The Chicago Data Portal field names change between dataset versions.
  Check the actual response keys before hardcoding column names.
  Implement a field name detection step:
  ```python
  lon_col = next(c for c in df.columns if "lon" in c.lower())
  lat_col = next(c for c in df.columns if "lat" in c.lower())
  name_col = next(c for c in df.columns if "name" in c.lower())
  ```
- Some records may have null coordinates. Drop rows where longitude or
  latitude is null or zero:
  ```python
  df = df[df["longitude"].notna() & df["latitude"].notna()]
  df = df[(df["longitude"].astype(float) != 0) &
          (df["latitude"].astype(float) != 0)]
  ```
- The dataset may mix urgent care with general health clinics, community
  health centres, and hospitals. For this analysis, include all of them —
  any facility offering urgent/walk-in care counts. If the dataset has too
  few "urgent care" records, broaden the filter.

---

## Dataset 4: Chicago Road Network

**What it is**: The complete driveable road network for Chicago from
OpenStreetMap. Downloaded as a NetworkX graph where nodes are intersections
and edges are road segments with speed and travel time attributes.

**Source**: OpenStreetMap via OSMnx

**Code**:
```python
import osmnx as ox
ox.settings.timeout = 300
ox.settings.log_console = True

G = ox.graph_from_place("Chicago, Illinois, USA", network_type="drive")
G = ox.add_edge_speeds(G, fallback=25)    # km/h
G = ox.add_edge_travel_times(G)           # seconds
ox.save_graphml(G, "data/raw/network/chicago_drive.graphml")
```

**`network_type="drive"` includes**: motorways, trunk roads, primary,
secondary, tertiary, residential, and unclassified roads — all roads
that cars can legally use.

**`ox.add_edge_speeds()`**: Assigns speed (km/h) to each edge based on:
1. The OSM `maxspeed` tag, if present
2. The speed lookup table in `config.ROAD_SPEEDS` by highway type
3. The `fallback` value (25 km/h) if neither is available

**`ox.add_edge_travel_times()`**: Computes `travel_time` in seconds for
each edge as `length / (speed_kph / 3.6)`.

**Graph format**: GraphML (XML-based, preserves all node and edge attributes)

**Node attributes** (relevant ones):
| Attribute | Type | Description |
|---|---|---|
| `osmid` | int | OpenStreetMap node ID |
| `x` | float | Longitude (WGS84) |
| `y` | float | Latitude (WGS84) |

**Edge attributes** (relevant ones):
| Attribute | Type | Description |
|---|---|---|
| `length` | float | Edge length in metres |
| `highway` | string | OSM road type |
| `maxspeed` | string | Speed limit (may be missing) |
| `speed_kph` | float | Assigned speed in km/h (added by OSMnx) |
| `travel_time` | float | Travel time in seconds (added by OSMnx) |

**Expected graph size**:
- Nodes: ~200,000–400,000 (road intersections)
- Edges: ~500,000–900,000 (road segments, directed)
- File size: 50–200MB as GraphML

**Download time**: 2–5 minutes on a typical home connection

**Known issues**:
- OSMnx queries the Overpass API. The API has rate limits and can timeout
  for large cities. Setting `ox.settings.timeout = 300` (5 minutes) prevents
  premature timeout failures.
- The graph is directed — most roads are bidirectional but are stored as
  two directed edges. This is correct for drive-time analysis.
- Some edges have `travel_time = 0` or very small values due to very short
  road segments. These are fine — they don't affect the isochrone meaningfully.
- If the download fails mid-way, it cannot be resumed. The entire graph must
  be re-downloaded.

---

## Dataset 5: Chicago City Boundary

**What it is**: The official city limits polygon for Chicago. Used to clip
all other layers to the city extent in Stage 2.

**Source**: US Census Bureau TIGER via pygris (places layer)

**Code**:
```python
import pygris
places = pygris.places(state="17")
chicago = places[places["NAME"] == "Chicago"]
```

**Alternative via OSMnx**:
```python
import osmnx as ox
chicago = ox.geocode_to_gdf("Chicago, Illinois, USA")
```

**Output format**: GeoJSON, EPSG:4326
**Expected geometry**: 1 Polygon or MultiPolygon

**Validation**: After reprojection to EPSG:26916, the area should be
approximately 589 km² (589,000,000 m²). In square metres at EPSG:26916
units: ~5.89 × 10⁸ m².

**Known issues**:
- The pygris places layer may return a MultiPolygon if Chicago's boundary
  is complex. This is fine — `gpd.clip()` handles both Polygon and MultiPolygon.

---

## Speed Assumptions

The `config.ROAD_SPEEDS` dictionary maps OSM highway tags to speeds in km/h.
These are conservative urban estimates — Chicago traffic is slower than the
posted speed limit. If you want to model free-flow conditions, increase speeds.

| Road type | Speed (km/h) | Rationale |
|---|---|---|
| motorway | 100 | Chicago expressways, free-flow |
| motorway_link | 60 | On/off ramps |
| trunk | 80 | Major arterials like Lake Shore Drive |
| primary | 50 | Main city streets |
| secondary | 40 | Secondary arterials |
| tertiary | 30 | Neighbourhood through-streets |
| residential | 25 | Residential grid streets |
| living_street | 15 | Pedestrian-priority streets |

These speeds produce 10-minute isochrones covering roughly 2–8 km from a
clinic depending on the surrounding road network density.

---

## Licences

| Dataset | Licence | Attribution |
|---|---|---|
| Census TIGER / ACS | Public domain | None required |
| Chicago Data Portal | City of Chicago Open Data | "City of Chicago" |
| OpenStreetMap | ODbL | "© OpenStreetMap contributors" |

Include OSM and City of Chicago attributions in the QGIS print layout
source citations box.

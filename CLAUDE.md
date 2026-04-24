# CLAUDE.md — Build Instructions for Claude Code

This file tells Claude Code exactly how to build the Chicago Urgent Care
Accessibility Analysis pipeline. Read this file completely before writing
any code. Also read ARCHITECTURE.md, DATA_SOURCES.md, and PIPELINE.md
before starting.

---

## Project Summary

Build a Python geospatial pipeline that:
1. Downloads 4 open datasets (Census, Chicago Data Portal, OSMnx, TIGER)
2. Reprojects everything to EPSG:26916 (UTM Zone 16N, metres)
3. Builds a NetworkX road graph and generates drive-time isochrones
4. Scores every Chicago census tract by unmet healthcare need (gap score)
5. Exports a GeoPackage for QGIS + a programmatic one-page PDF brief

The key differentiator from a basic buffer analysis is Stage 3: real
drive-time isochrones computed on the OpenStreetMap road network using
Dijkstra's algorithm, not circular buffers.

---

## Before You Write Any Code

Read these files in order:
1. `README.md` — project overview
2. `ARCHITECTURE.md` — design decisions and data flow
3. `DATA_SOURCES.md` — exact URLs, fields, and formats
4. `PIPELINE.md` — stage-by-stage implementation details

Do not invent data sources. Do not change the CRS. Do not change the
file structure. Follow these documents exactly.

---

## Critical Rules

### CRS Rule
Every GeoDataFrame MUST be in EPSG:26916 before any spatial operation.
EPSG:26916 is WGS 84 / UTM Zone 16N. Units are metres.

Do NOT use EPSG:4326 for any spatial operation — degrees are not metres.

Assert CRS before every spatial operation:
```python
assert gdf.crs.to_epsg() == 26916, f"Expected EPSG:26916, got {gdf.crs}"
```

### Data Isolation Rule
Raw data in `data/raw/` is never modified. Each stage reads from the
previous stage's output and writes to its own output directory.

### Config Rule
Every magic number comes from `config.py`. No hardcoded numbers anywhere
in pipeline modules. This includes travel time thresholds, speed assumptions,
CRS codes, file paths, and all Chicago-specific constants.

### Error Handling Rule
Every stage function must:
- Check that expected input files exist before running
- Raise `FileNotFoundError` with a helpful message if they do not
- Log progress at every major step using `logging` (not `print`)
- Validate geometry after every spatial operation

### Geometry Validation Rule
After every spatial operation:
```python
gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()]
gdf = gdf[gdf.geometry.is_valid]
```

### Network Graph Rule
The OSMnx road graph is large. Save it to disk after downloading in Stage 1
using `osmnx.save_graphml()`. Load it from disk in Stage 3 using
`osmnx.load_graphml()`. Never re-download the graph inside Stage 3.

### Live API Inspection Rule
Live APIs do not match their documentation. Field names drift, dataset IDs
change, and response shapes are not what the docs promised. The Chicago Data
Portal is the most likely place this bites us in this project — the clinic
dataset's coordinate fields may be called `longitude`/`latitude`, `long`/`lat`,
`x_coordinate`/`y_coordinate`, or may arrive as a nested `location` object.

Before parsing any response from a live API, log what actually came back:

```python
logger.info(f"Chicago Portal columns: {df.columns.tolist()}")
logger.info(f"First record sample: {df.iloc[0].to_dict()}")
```

Do this for every live-API download (clinics especially, but also Census ACS).
Then use defensive column detection rather than hard-coded field names:

```python
lon_col = next((c for c in df.columns if "lon" in c.lower()), None)
lat_col = next((c for c in df.columns if "lat" in c.lower()), None)
if lon_col is None or lat_col is None:
    raise ValueError(f"Could not find lon/lat columns in: {df.columns.tolist()}")
```

If the API returns zero results or an unexpected shape, log the raw response
and raise a clear error rather than silently producing an empty GeoDataFrame.

### 95% Confidence Rule
Before moving from one step to the next, be at least 95% sure the current
step is correct and heading in the right direction. If there's meaningful
doubt — an API returned something you didn't expect, a field count looks
wrong, a CRS assertion is borderline, a test passed for a reason you can't
explain — stop and investigate before building on top of it. Small uncertainty
at Stage 1 becomes a broken map at Stage 5. "Seems to work" is not 95%.
Actually looking at the output and confirming it matches what you expected
is 95%.

### Plan → Execute → Test → Next Rule
Work one thing at a time in this exact order:

1. **Plan** the next piece of work — know what you're about to write and why
   before you write it.
2. **Execute** — implement that one piece.
3. **Test** it — run it, look at the output, confirm it does what you planned.
   For a download function, that means opening the file and checking the
   contents. For a spatial operation, that means printing the CRS, row count,
   and a geometry sample. For a scoring function, that means spot-checking
   a few tracts by hand.
4. **Only then** move to the next piece.

Do not stack multiple unverified steps on top of each other. Do not write
Stage 3 before Stage 2's output has been inspected. Do not write the PDF
export before the gap scores have been eyeballed. Each step stands on a
tested foundation, not a hoped-for one.

---

## File-by-File Build Instructions

### config.py

Build this first. All other files import from it.

```python
# CRS
PROJECT_CRS  = "EPSG:26916"    # WGS 84 / UTM Zone 16N (metres)
DOWNLOAD_CRS = "EPSG:4326"     # WGS84, used only for raw downloads

# Travel time thresholds in seconds
TRAVEL_TIME_10MIN = 600        # 10 minutes = 600 seconds
TRAVEL_TIME_20MIN = 1200       # 20 minutes = 1200 seconds

# Road speed assumptions in km/h
# Based on OSM highway tag values
ROAD_SPEEDS = {
    "motorway":       100,
    "motorway_link":   60,
    "trunk":           80,
    "trunk_link":      50,
    "primary":         50,
    "primary_link":    40,
    "secondary":       40,
    "secondary_link":  30,
    "tertiary":        30,
    "tertiary_link":   25,
    "residential":     25,
    "living_street":   15,
    "unclassified":    25,
    "road":            25,
}

DEFAULT_SPEED = 25  # km/h fallback for unknown road types

# Chicago FIPS codes
STATE_FIPS  = "17"             # Illinois
COUNTY_FIPS = "031"            # Cook County
COUNTY_FULL = "17031"

# Chicago OSMnx query string
CHICAGO_PLACE = "Chicago, Illinois, USA"
NETWORK_TYPE  = "drive"        # driveable roads only

# Gap scoring
# gap_score = population * (1 - coverage_fraction_10min)
# Using 10-minute coverage as the primary threshold
PRIMARY_THRESHOLD   = "10min"
SECONDARY_THRESHOLD = "20min"

# Top N recommended locations to output
TOP_N_RECOMMENDATIONS = 3

# Data paths
DATA_RAW       = "data/raw"
DATA_PROCESSED = "data/processed"
OUTPUTS        = "outputs"

RAW_CENSUS    = "data/raw/census"
RAW_CLINICS   = "data/raw/clinics"
RAW_NETWORK   = "data/raw/network"
RAW_BOUNDARY  = "data/raw/boundary"

PROCESSED_S2  = "data/processed/stage2"
PROCESSED_S3  = "data/processed/stage3"
PROCESSED_S4  = "data/processed/stage4"

# Raw file paths
TRACTS_RAW    = "data/raw/census/tracts.geojson"
POPULATION_RAW = "data/raw/census/population.csv"
CLINICS_RAW   = "data/raw/clinics/urgent_care.geojson"
GRAPH_RAW     = "data/raw/network/chicago_drive.graphml"
BOUNDARY_RAW  = "data/raw/boundary/chicago_boundary.geojson"

# Processed file paths — Stage 2
TRACTS_S2     = "data/processed/stage2/tracts.gpkg"
CLINICS_S2    = "data/processed/stage2/clinics.gpkg"
BOUNDARY_S2   = "data/processed/stage2/chicago_boundary.gpkg"

# Processed file paths — Stage 3
ISO_10MIN_S3  = "data/processed/stage3/isochrones_10min.gpkg"
ISO_20MIN_S3  = "data/processed/stage3/isochrones_20min.gpkg"

# Processed file paths — Stage 4
TRACTS_S4     = "data/processed/stage4/tracts_scored.gpkg"
GAP_POINTS_S4 = "data/processed/stage4/gap_points.gpkg"

# Output files
FINAL_GPKG    = "outputs/chicago_accessibility.gpkg"
BRIEF_PDF     = "outputs/brief.pdf"

# GeoPackage layer names
GPKG_TRACTS      = "tracts_scored"
GPKG_ISO_10      = "isochrones_10min"
GPKG_ISO_20      = "isochrones_20min"
GPKG_CLINICS     = "clinics"
GPKG_GAP_POINTS  = "gap_points"

# All directories to create on setup
ALL_DIRS = [
    RAW_CENSUS, RAW_CLINICS, RAW_NETWORK, RAW_BOUNDARY,
    PROCESSED_S2, PROCESSED_S3, PROCESSED_S4,
    OUTPUTS, "notebooks",
]
```

---

### pipeline/ingest.py

Downloads all raw data. No spatial operations. No reprojection.
Skip any file that already exists (check with `os.path.exists()`).

**`download_census_tracts(output_dir)`**
- Use `pygris.tracts(state="17", county="031", year=2020)`
- Keep fields: `GEOID`, `NAME`, `AREALAND`, `AREAWATER`, geometry
- Save to `data/raw/census/tracts.geojson`
- Expected: ~801 tracts in Cook County
- Note: Cook County is larger than Chicago city limits. The city boundary
  clip in Stage 2 will reduce this to Chicago tracts only (~800 tracts).

**`download_population_data(output_dir)`**
- Census ACS 5-year, Table B01003 (total population)
- API URL: `https://api.census.gov/data/2022/acs/acs5`
- Parameters: `get=B01003_001E,GEO_ID`, `for=tract:*`, `in=state:17 county:031`
- Rename `B01003_001E` → `population`
- Cast to int; replace Census null sentinel `-666666666` with 0
- Save to `data/raw/census/population.csv`

**`download_clinics(output_dir)`**
- Chicago Data Portal Socrata API
- Dataset: "Public Health Statistics — Selected public health indicators by
  Chicago community area" is NOT the right one.
- Use the correct dataset: search Chicago Data Portal for
  "Health and Human Services" or "Urgent Care"
- Primary URL to try:
  `https://data.cityofchicago.org/resource/iqnk-2tcu.json`
  This is the "Health Care Facilities" dataset.
- If that returns no results, fall back to querying:
  `https://data.cityofchicago.org/resource/f5ex-mxwn.json`
  Filter by `facility_type` containing "urgent" or "clinic"
- Parameters: `$limit=5000`, `$where=facility_type like '%URGENT%'`
- Before touching the response, log what actually came back (see Live API
  Inspection Rule):
  ```python
  logger.info(f"Chicago Portal columns: {df.columns.tolist()}")
  logger.info(f"First record sample: {df.iloc[0].to_dict()}")
  ```
- Each record *should* have `longitude` and `latitude` fields — but the real
  field names may differ. Use defensive detection:
  ```python
  lon_col = next((c for c in df.columns if "lon" in c.lower()), None)
  lat_col = next((c for c in df.columns if "lat" in c.lower()), None)
  ```
- Create GeoDataFrame from coordinates, CRS EPSG:4326
- Save to `data/raw/clinics/urgent_care.geojson`
- Log the number of clinics downloaded
- IMPORTANT: If the Chicago Data Portal returns zero urgent care clinics,
  fall back to downloading ALL health facilities and filtering to
  facility_type containing "CLINIC", "URGENT", or "HEALTH CENTER"
- Expected: 50–200 clinics/health facilities

**`download_road_network(output_dir)`**
- This is the most time-consuming download — 2–5 minutes
- Use OSMnx to download the driveable road network for Chicago:
  ```python
  import osmnx as ox
  ox.settings.timeout = 300
  ox.settings.log_console = True
  G = ox.graph_from_place("Chicago, Illinois, USA", network_type="drive")
  ```
- Add speed and travel time to every edge:
  ```python
  G = ox.add_edge_speeds(G)
  G = ox.add_edge_travel_times(G)
  ```
- Save using GraphML format (preserves all attributes):
  ```python
  ox.save_graphml(G, "data/raw/network/chicago_drive.graphml")
  ```
- Log the number of nodes and edges in the graph
- Expected: ~200,000–400,000 nodes, ~500,000–900,000 edges

**`download_city_boundary(output_dir)`**
- Use pygris to get Chicago city limits (place boundary):
  ```python
  import pygris
  chicago = pygris.places(state="17")
  chicago = chicago[chicago["NAME"] == "Chicago"]
  ```
- Save to `data/raw/boundary/chicago_boundary.geojson`
- Validate: result should be 1 polygon/multipolygon
- Alternative: use OSMnx geocode:
  ```python
  chicago = ox.geocode_to_gdf("Chicago, Illinois, USA")
  ```

**`run()`**
- Create all `data/raw/` subdirectories
- Call all download functions in order
- Log file sizes after each download
- Skip any file that already exists unless `force=True`

---

### pipeline/reproject.py

Reprojects, validates, and clips all raw data to EPSG:26916.

Same pattern as Project 1's reproject.py. Apply this template to every layer:

```python
def process_layer(raw_path, boundary_gdf, output_path, keep_cols=None,
                  geometry_types=None):
    gdf = gpd.read_file(raw_path)
    logger.info(f"Loaded {len(gdf)} features, CRS: {gdf.crs}")

    gdf = gdf.to_crs("EPSG:26916")

    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty & gdf.geometry.is_valid]

    if geometry_types:
        gdf = gdf[gdf.geometry.geom_type.isin(geometry_types)]

    if keep_cols:
        gdf = gdf[keep_cols + ["geometry"]]

    gdf = gpd.clip(gdf, boundary_gdf)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]

    logger.info(f"After clip: {len(gdf)} features")
    gdf.to_file(output_path, driver="GPKG")
    return gdf
```

**`process_census_tracts(raw_dir, processed_dir, boundary_gdf)`**
- Load `data/raw/census/tracts.geojson`
- Load `data/raw/census/population.csv`
- Build join key: `population_df["GEOID"] = population_df["GEO_ID"].str[-11:]`
- Left join population onto tracts on GEOID
- Add `area_sqm` column: `tracts["area_sqm"] = tracts.geometry.area`
  (in EPSG:26916 the unit is metres, so area is square metres)
- Reproject to EPSG:26916
- Clip to Chicago boundary
- Log: how many of the ~800 tracts joined population successfully
- Save to `data/processed/stage2/tracts.gpkg`

**`process_clinics(raw_dir, processed_dir, boundary_gdf)`**
- Load `data/raw/clinics/urgent_care.geojson`
- Reproject to EPSG:26916
- Clip to Chicago boundary
- Keep: `name` (or `facility_name`), geometry
- Save to `data/processed/stage2/clinics.gpkg`
- Log how many clinics remain after clip

**`process_boundary(raw_dir, processed_dir)`**
- Load `data/raw/boundary/chicago_boundary.geojson`
- Reproject to EPSG:26916
- Save to `data/processed/stage2/chicago_boundary.gpkg`
- Return the boundary GDF (used by all other process functions)

**`run()`**
- Call `process_boundary()` first to get the clipping mask
- Then call `process_census_tracts()` and `process_clinics()`
- Assert all output files exist and are non-empty
- Note: the road network graph is NOT processed here — it stays in
  `data/raw/network/` and is loaded directly in Stage 3 by OSMnx

---

### pipeline/network.py

This is the most technically complex stage. Read carefully.

**Purpose**: Generate drive-time isochrone polygons from each clinic
using real road network analysis.

**Key concept**: An isochrone is a polygon representing "everywhere you can
drive to from this point in X minutes." Unlike a circular buffer, it follows
the actual road network, so a clinic near a highway has a much larger
10-minute isochrone than one in a dense grid neighbourhood.

**`load_graph(graphml_path)`**
- Load the saved GraphML file:
  ```python
  G = ox.load_graphml(graphml_path)
  ```
- Verify the graph has `travel_time` on edges:
  ```python
  sample_edge = list(G.edges(data=True))[0]
  assert "travel_time" in sample_edge[2], "Graph missing travel_time attribute"
  ```
- If `travel_time` is missing, recompute:
  ```python
  G = ox.add_edge_speeds(G, fallback=25)
  G = ox.add_edge_travel_times(G)
  ```
- Log: number of nodes and edges
- Return G

**`get_nearest_node(G, point_geom)`**
- Given a Shapely Point geometry (in EPSG:26916), find the nearest
  OSM graph node.
- OSMnx's `nearest_nodes` expects lon/lat in EPSG:4326. Reproject the point:
  ```python
  from pyproj import Transformer
  transformer = Transformer.from_crs("EPSG:26916", "EPSG:4326", always_xy=True)
  lon, lat = transformer.transform(point_geom.x, point_geom.y)
  node_id = ox.nearest_nodes(G, lon, lat)
  ```
- Return node_id

**`generate_isochrone(G, node_id, travel_time_seconds)`**
- Use NetworkX to find all nodes reachable within `travel_time_seconds`:
  ```python
  import networkx as nx
  subgraph = nx.ego_graph(G, node_id, radius=travel_time_seconds,
                          distance="travel_time")
  ```
- Extract the (x, y) coordinates of all nodes in the subgraph:
  ```python
  node_points = [
      (data["x"], data["y"])   # OSMnx stores lon/lat in x/y
      for node, data in subgraph.nodes(data=True)
  ]
  ```
- Build a polygon from these points using convex hull:
  ```python
  from shapely.geometry import MultiPoint
  if len(node_points) < 3:
      return None
  isochrone_poly = MultiPoint(node_points).convex_hull
  ```
- The node coordinates are in EPSG:4326 (lon/lat). After building the polygon,
  create a GeoSeries and reproject to EPSG:26916:
  ```python
  iso_gdf = gpd.GeoDataFrame({"geometry": [isochrone_poly]}, crs="EPSG:4326")
  iso_gdf = iso_gdf.to_crs("EPSG:26916")
  return iso_gdf.geometry.iloc[0]
  ```
- Return a Shapely geometry in EPSG:26916, or None if too few nodes

**`generate_all_isochrones(G, clinics_gdf, travel_times)`**
- `travel_times` is a list of ints: `[600, 1200]` (from config.py)
- For each clinic:
  - Find nearest graph node
  - For each travel time threshold: generate isochrone polygon
  - Store result with clinic name and travel time
- Return a dict:
  ```python
  {
      600:  GeoDataFrame of all per-clinic 10-min isochrones,
      1200: GeoDataFrame of all per-clinic 20-min isochrones,
  }
  ```
- Log progress: "Clinic 5/47: Chicago Medical Center — 10min OK, 20min OK"
- Handle errors: if a clinic fails (e.g. nearest node is outside the graph),
  log a warning and skip it — do not crash the whole stage.

**`dissolve_isochrones(iso_gdf)`**
- Dissolve all per-clinic isochrones into a single union polygon:
  ```python
  dissolved = iso_gdf.copy()
  dissolved["dissolve_key"] = 1
  dissolved = dissolved.dissolve(by="dissolve_key").reset_index(drop=True)
  ```
- This gives the total city-wide service area at that travel time
- Validate: result should be 1 row (a single MultiPolygon or Polygon)
- Return as GeoDataFrame

**`run()`**
- Load graph from `data/raw/network/chicago_drive.graphml`
- Load clinics from `data/processed/stage2/clinics.gpkg`
- Assert clinics CRS is EPSG:26916
- Call `generate_all_isochrones()`
- Dissolve each threshold's isochrones
- Save to:
  - `data/processed/stage3/isochrones_10min.gpkg` — dissolved 10-min coverage
  - `data/processed/stage3/isochrones_20min.gpkg` — dissolved 20-min coverage
  - `data/processed/stage3/isochrones_10min_individual.gpkg` — per-clinic 10-min
  - `data/processed/stage3/isochrones_20min_individual.gpkg` — per-clinic 20-min
- Log: total area covered (sq km) at 10 min and 20 min
- Log: percentage of Chicago's total area covered at each threshold

---

### pipeline/gap.py

Computes the gap score per tract. This is the scoring logic.

**`compute_coverage_fraction(tracts_gdf, isochrone_gdf, col_name)`**
- For each census tract, compute what fraction of its area falls inside
  the dissolved isochrone:
  ```python
  tracts_gdf = tracts_gdf.copy()

  iso_union = isochrone_gdf.geometry.unary_union

  tracts_gdf[col_name] = tracts_gdf.geometry.apply(
      lambda geom: (
          geom.intersection(iso_union).area / geom.area
          if geom.area > 0 else 0.0
      )
  )
  tracts_gdf[col_name] = tracts_gdf[col_name].clip(0.0, 1.0)
  ```
- `col_name` will be `"coverage_10min"` or `"coverage_20min"`
- Use spatial index for performance (same STRtree pattern as Project 1)
- Return tracts_gdf with new column added

**`compute_gap_scores(tracts_gdf)`**
- Compute gap scores using 10-minute coverage as primary metric:
  ```python
  tracts_gdf["gap_score"] = (
      tracts_gdf["population"] * (1.0 - tracts_gdf["coverage_10min"])
  )
  ```
- Also compute a secondary 20-min gap score for the brief:
  ```python
  tracts_gdf["gap_score_20min"] = (
      tracts_gdf["population"] * (1.0 - tracts_gdf["coverage_20min"])
  )
  ```
- Round both to 2 decimal places
- Validate: no NaN in gap_score; all values >= 0
- Return tracts_gdf

**`identify_top_gaps(tracts_gdf, n)`**
- Sort tracts by `gap_score` descending
- Take the top `n` (from config.TOP_N_RECOMMENDATIONS = 3)
- For each, compute the centroid — this is the recommended location
- Create a new GeoDataFrame of just these centroid points:
  ```python
  top_tracts = tracts_gdf.nlargest(n, "gap_score").copy()
  top_tracts["geometry"] = top_tracts.geometry.centroid
  top_tracts["rank"] = range(1, n + 1)
  top_tracts["recommendation"] = top_tracts.apply(
      lambda row: f"Rank {int(row['rank'])}: {row['NAME']} — "
                  f"Population: {int(row['population']):,} — "
                  f"10min coverage: {row['coverage_10min']:.1%}",
      axis=1
  )
  ```
- Return GeoDataFrame of top-N recommended clinic locations

**`gap_summary(tracts_gdf)`**
- Print a summary:
  - Total Chicago population
  - Population within 10-min of any existing clinic (covered)
  - Population NOT within 10-min (uncovered)
  - % covered at 10 min and 20 min
  - Top 10 most underserved tracts (GEOID, name, population, gap_score)
- This is printed to the console and also used to populate the PDF brief

**`run()`**
- Load `data/processed/stage2/tracts.gpkg`
- Load `data/processed/stage3/isochrones_10min.gpkg`
- Load `data/processed/stage3/isochrones_20min.gpkg`
- Assert all GDFs are EPSG:26916
- Run `compute_coverage_fraction()` for both thresholds
- Run `compute_gap_scores()`
- Run `identify_top_gaps()`
- Call `gap_summary()` and store the stats dict for export
- Save to `data/processed/stage4/tracts_scored.gpkg`
- Save to `data/processed/stage4/gap_points.gpkg`

---

### pipeline/export.py

Two outputs: GeoPackage and PDF brief.

**`build_geopackage(output_path)`**
- Load all layers and write to GeoPackage:
  ```
  tracts_scored       ← stage4/tracts_scored.gpkg
  isochrones_10min    ← stage3/isochrones_10min.gpkg
  isochrones_20min    ← stage3/isochrones_20min.gpkg
  clinics             ← stage2/clinics.gpkg
  gap_points          ← stage4/gap_points.gpkg
  ```
- First layer: `mode="w"`, all subsequent: `mode="a"`
- Validate all layers exist and are non-empty after writing

**`build_pdf_brief(output_path, tracts_gdf, gap_points_gdf, stats)`**
- Use `reportlab` to generate a one-page PDF
- Install: `pip install reportlab`
- Layout:
  ```
  [Title]
  Chicago Urgent Care Accessibility Analysis
  Recommendations for New Clinic Locations

  [Section 1: Coverage Summary]
  Total Chicago population: X
  Population within 10-min drive of a clinic: X (XX%)
  Population NOT within 10-min drive: X (XX%)

  [Section 2: Top 10 Underserved Census Tracts]
  Rank | Tract | Community Area | Population | 10-min Coverage | Gap Score
  ...table of 10 rows...

  [Section 3: Top 3 Recommended Locations]
  For each of the 3 recommended locations:
    Rank N
    Tract: [NAME]
    Coordinates: [lat, lon in WGS84]
    Population: [X]
    Current 10-min coverage: [X%]
    Gap score: [X]
    Justification: [1–2 sentences]

  [Footer]
  Data sources + methodology note + date
  ```
- ReportLab basic setup:
  ```python
  from reportlab.lib.pagesizes import letter
  from reportlab.lib.styles import getSampleStyleSheet
  from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, Spacer
  from reportlab.lib import colors

  doc = SimpleDocTemplate(output_path, pagesize=letter)
  styles = getSampleStyleSheet()
  story = []
  # ... build story elements ...
  doc.build(story)
  ```
- Convert gap point coordinates from EPSG:26916 to EPSG:4326 for the brief:
  ```python
  gap_wgs84 = gap_points_gdf.to_crs("EPSG:4326")
  lat = gap_wgs84.geometry.iloc[i].y
  lon = gap_wgs84.geometry.iloc[i].x
  ```

**`run()`**
- Call `build_geopackage()`
- Load tracts_scored and gap_points for the brief
- Compute stats dict (total pop, covered pop, % covered)
- Call `build_pdf_brief()`
- Log both output file paths and sizes

---

### run_pipeline.py

Same structure as Project 1. Stages are: `ingest`, `reproject`, `network`,
`gap`, `export`.

```python
STAGES = ["ingest", "reproject", "network", "gap", "export"]
```

Support `--setup`, `--stage`, `--from-stage`, and `--force` flags.

---

## Common Mistakes to Avoid

1. **OSMnx node coordinates are in EPSG:4326 (lon/lat).** When you extract
   node positions from the graph (`G.nodes[node_id]["x"]` and `["y"]`), these
   are longitude and latitude respectively, NOT projected coordinates.
   Always build isochrone polygons in EPSG:4326 first, then reproject to EPSG:26916.

2. **NetworkX ego_graph uses travel_time as the distance metric.**
   Make sure to pass `distance="travel_time"` — the default `distance=None`
   counts hops (number of road segments), not time.

3. **The graph is large.** `ox.load_graphml()` for Chicago takes 30–60 seconds
   and uses significant memory (~2GB). Do not re-load it inside a loop.
   Load once at the top of `network.py`'s `run()` function and pass it around.

4. **Cook County ≠ Chicago.** The Census tract download uses Cook County FIPS
   (17031), which includes many suburbs. The city boundary clip in Stage 2
   reduces this to Chicago proper. Expect to go from ~1300 Cook County tracts
   down to ~800 Chicago tracts after clipping.

5. **Chicago Data Portal endpoint may change.** If the primary clinics URL
   returns no results, implement a fallback. See `ingest.py` instructions for
   the fallback strategy.

6. **Isochrone polygons need a minimum of 3 nodes** to form a valid polygon.
   If a clinic has fewer than 3 reachable nodes (e.g. it's in a dead end),
   `MultiPoint().convex_hull` returns a Point or LineString, not a Polygon.
   Check for this and skip that clinic.

7. **Never buffer in EPSG:4326.** Same rule as Project 1. All spatial operations
   in EPSG:26916.

8. **GeoPackage append mode.** First layer: `mode="w"`. All others: `mode="a"`.
   Using `mode="w"` for all overwrites the file each time.

9. **ReportLab table cell widths.** ReportLab does not auto-size table columns.
   Specify column widths manually in points (1 inch = 72 points):
   ```python
   table = Table(data, colWidths=[30, 120, 100, 60, 80, 70])
   ```

10. **Convex hull vs alpha shape.** This pipeline uses convex hull for isochrone
    polygon construction. This is a simplification — concave areas (parks,
    industrial zones without roads) will be included. Alpha shapes give more
    accurate concave isochrones but require the `alphashape` library. Convex
    hull is acceptable for a portfolio project.

---

## Expected Outputs After Each Stage

After **Stage 1 (ingest)**:
- `data/raw/census/tracts.geojson` — ~1300 Cook County tracts
- `data/raw/census/population.csv` — ~1300 rows
- `data/raw/clinics/urgent_care.geojson` — 50–200 clinics
- `data/raw/network/chicago_drive.graphml` — large file, 50–200MB
- `data/raw/boundary/chicago_boundary.geojson` — 1 polygon

After **Stage 2 (reproject)**:
- All files in EPSG:26916
- `data/processed/stage2/tracts.gpkg` — ~800 Chicago tracts with population
- `data/processed/stage2/clinics.gpkg` — clinics within Chicago boundary

After **Stage 3 (network)**:
- `data/processed/stage3/isochrones_10min.gpkg` — 1 dissolved polygon
- `data/processed/stage3/isochrones_20min.gpkg` — 1 dissolved polygon
- `data/processed/stage3/isochrones_10min_individual.gpkg` — one per clinic
- `data/processed/stage3/isochrones_20min_individual.gpkg` — one per clinic

After **Stage 4 (gap)**:
- `data/processed/stage4/tracts_scored.gpkg` — tracts with coverage + gap score
- `data/processed/stage4/gap_points.gpkg` — 3 recommended location points

After **Stage 5 (export)**:
- `outputs/chicago_accessibility.gpkg` — 5 layers
- `outputs/brief.pdf` — one-page recommendation brief

---

## QGIS Instructions (Post-Pipeline)

1. Open QGIS → New Project
2. Set project CRS to EPSG:26916
3. Drag `outputs/chicago_accessibility.gpkg` into the Layers panel
4. Style `tracts_scored` — Graduated, column `gap_score`, colour ramp
   "Blues to Reds" inverted (or "RdYlBu" reversed), 5 Natural Breaks classes
5. Add `isochrones_10min` — transparent fill, blue stroke, 30% opacity
6. Add `clinics` — small dark circle markers
7. Add `gap_points` — large red star markers labelled "Recommended"
8. Print Layout:
   - A3 landscape
   - Main map covering Chicago
   - Inset map (small) showing Chicago's location in Illinois
   - Title: "Chicago Urgent Care Accessibility — Drive-Time Gap Analysis"
   - Legend, scale bar, north arrow
   - Source citations
9. Export as PDF + PNG to `outputs/maps/`

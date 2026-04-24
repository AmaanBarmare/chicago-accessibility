# PIPELINE.md — Stage-by-Stage Implementation Guide

This document walks through every stage in implementation order.
It is a companion to CLAUDE.md. Where CLAUDE.md specifies what to build,
this document explains how each stage works conceptually.

---

## Running the Pipeline

```bash
# Full run from scratch
python run_pipeline.py

# Setup directories only
python run_pipeline.py --setup

# Single stage
python run_pipeline.py --stage network

# From a specific stage onwards (most useful during development)
python run_pipeline.py --from-stage gap
```

The most important flag for this project is `--from-stage network`. Stage 3
takes 5–15 minutes. Once isochrones are computed and saved, rerun gap and
export instantly by starting from Stage 4.

---

## Stage 0: Environment Setup

```bash
pip install geopandas osmnx networkx shapely pandas requests pyproj fiona \
            reportlab matplotlib contextily pygris python-dotenv
```

Create directories:
```bash
python run_pipeline.py --setup
```

Set your Census API key in `.env`:
```
CENSUS_API_KEY=your_key_here
```

---

## Stage 1: Ingest (`pipeline/ingest.py`)

**Purpose**: Download all raw data. No spatial operations, no reprojection.

**Reads**: Nothing.

**Writes**:
- `data/raw/census/tracts.geojson`
- `data/raw/census/population.csv`
- `data/raw/clinics/urgent_care.geojson`
- `data/raw/network/chicago_drive.graphml`
- `data/raw/boundary/chicago_boundary.geojson`

**Key behaviour**: Skip downloads if files exist. The graph download is the
largest (50–200MB) and slowest (2–5 min). Log progress clearly so you know
which download is running.

### Census Tracts

```python
import pygris
tracts = pygris.tracts(state="17", county="031", year=2020)
tracts = tracts[["GEOID", "NAME", "AREALAND", "geometry"]]
tracts.to_file("data/raw/census/tracts.geojson", driver="GeoJSON")
```

### Population Data

```python
import requests, pandas as pd

url = "https://api.census.gov/data/2022/acs/acs5"
params = {
    "get": "B01003_001E,GEO_ID",
    "for": "tract:*",
    "in": "state:17 county:031",
    "key": os.getenv("CENSUS_API_KEY", "")
}
response = requests.get(url, params=params).json()
headers, *rows = response
df = pd.DataFrame(rows, columns=headers)
df = df.rename(columns={"B01003_001E": "population"})
df["population"] = pd.to_numeric(df["population"], errors="coerce").fillna(0).astype(int)
df.loc[df["population"] < 0, "population"] = 0
df.to_csv("data/raw/census/population.csv", index=False)
```

### Clinics

```python
import requests, geopandas as gpd

url = "https://data.cityofchicago.org/resource/iqnk-2tcu.json"
params = {"$limit": 5000}
response = requests.get(url, params=params).json()
df = pd.DataFrame(response)

# Detect coordinate column names (they vary by dataset version)
lon_col = next((c for c in df.columns if "lon" in c.lower()), None)
lat_col = next((c for c in df.columns if "lat" in c.lower()), None)

if not lon_col or not lat_col:
    raise ValueError(f"Cannot find coordinate columns. Columns: {df.columns.tolist()}")

df = df.dropna(subset=[lon_col, lat_col])
df[lon_col] = df[lon_col].astype(float)
df[lat_col] = df[lat_col].astype(float)
df = df[(df[lon_col] != 0) & (df[lat_col] != 0)]

gdf = gpd.GeoDataFrame(
    df,
    geometry=gpd.points_from_xy(df[lon_col], df[lat_col]),
    crs="EPSG:4326"
)
gdf.to_file("data/raw/clinics/urgent_care.geojson", driver="GeoJSON")
logger.info(f"Downloaded {len(gdf)} clinic locations")
```

### Road Network

```python
import osmnx as ox

ox.settings.timeout = 300
ox.settings.log_console = True

logger.info("Downloading Chicago road network — this takes 2–5 minutes...")
G = ox.graph_from_place("Chicago, Illinois, USA", network_type="drive")
G = ox.add_edge_speeds(G, fallback=25)
G = ox.add_edge_travel_times(G)

nodes, edges = G.number_of_nodes(), G.number_of_edges()
logger.info(f"Graph downloaded: {nodes:,} nodes, {edges:,} edges")

ox.save_graphml(G, "data/raw/network/chicago_drive.graphml")
```

### City Boundary

```python
import pygris
places = pygris.places(state="17")
chicago = places[places["NAME"] == "Chicago"].copy()
chicago.to_file("data/raw/boundary/chicago_boundary.geojson", driver="GeoJSON")
```

---

## Stage 2: Reproject (`pipeline/reproject.py`)

**Purpose**: Clean, validate, reproject all raw files to EPSG:26916, clip to Chicago.

**Reads**: `data/raw/`

**Writes**: `data/processed/stage2/`

**Load boundary first** (used to clip everything else):
```python
boundary = gpd.read_file("data/raw/boundary/chicago_boundary.geojson")
boundary = boundary.to_crs("EPSG:26916")
boundary = boundary[boundary.geometry.notna() & boundary.geometry.is_valid]
boundary.to_file("data/processed/stage2/chicago_boundary.gpkg", driver="GPKG")
```

**Standard template** for every layer:
```python
def process_layer(raw_path, boundary_gdf, output_path, keep_cols=None):
    gdf = gpd.read_file(raw_path)
    gdf = gdf.to_crs("EPSG:26916")
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty & gdf.geometry.is_valid]
    if keep_cols:
        gdf = gdf[keep_cols + ["geometry"]]
    gdf = gpd.clip(gdf, boundary_gdf)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    gdf.to_file(output_path, driver="GPKG")
    return gdf
```

**Tracts + population join**:
```python
tracts = gpd.read_file("data/raw/census/tracts.geojson")
population = pd.read_csv("data/raw/census/population.csv")

# Build join key
population["GEOID"] = population["GEO_ID"].str[-11:]

tracts = tracts.merge(
    population[["GEOID", "population"]],
    on="GEOID",
    how="left"
)
tracts["population"] = tracts["population"].fillna(0).astype(int)

# Compute tract area in square metres (CRS is in metres)
tracts = tracts.to_crs("EPSG:26916")
tracts["area_sqm"] = tracts.geometry.area

joined = tracts["population"].notna().sum()
logger.info(f"Population joined for {joined}/{len(tracts)} tracts")
```

**Note**: The road network graph is NOT processed in Stage 2. OSMnx loads it
directly in Stage 3. The graph nodes are in EPSG:4326 internally — OSMnx
handles the coordinate system transparently.

---

## Stage 3: Network (`pipeline/network.py`)

This is the most technically complex stage. The core operation is:

```
Load graph → find nearest node for each clinic → run Dijkstra's → build polygon
```

### Understanding the Graph Structure

OSMnx graphs have:
- **Nodes**: road intersections. Each node has `x` (longitude) and `y` (latitude)
  in EPSG:4326.
- **Edges**: road segments between intersections. After `add_edge_travel_times()`,
  each edge has `travel_time` in seconds.
- The graph is a MultiDiGraph (directed, allows parallel edges between nodes).

### Loading the Graph

```python
import osmnx as ox
G = ox.load_graphml("data/raw/network/chicago_drive.graphml")
logger.info(f"Graph loaded: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
```

### Finding the Nearest Node to a Clinic

The clinics are in EPSG:26916 (metres). OSMnx's `nearest_nodes()` expects
EPSG:4326 (lon/lat). Convert before calling:

```python
from pyproj import Transformer
transformer = Transformer.from_crs("EPSG:26916", "EPSG:4326", always_xy=True)

def get_nearest_node(G, point_26916):
    lon, lat = transformer.transform(point_26916.x, point_26916.y)
    return ox.nearest_nodes(G, lon, lat)
```

### Dijkstra's Algorithm via NetworkX ego_graph

`nx.ego_graph()` returns the subgraph of all nodes reachable within a given
radius. With `distance="travel_time"`, it measures in seconds:

```python
import networkx as nx

subgraph = nx.ego_graph(
    G,
    node_id,
    radius=600,              # 600 seconds = 10 minutes
    distance="travel_time"
)
```

This is essentially Dijkstra's single-source shortest path, stopping at 600s.
The subgraph contains all nodes whose shortest travel time from `node_id` is
≤ 600 seconds.

### Building the Isochrone Polygon

Extract node coordinates and build a convex hull:

```python
from shapely.geometry import MultiPoint

node_points = [
    (data["x"], data["y"])   # lon, lat in EPSG:4326
    for node, data in subgraph.nodes(data=True)
]

if len(node_points) < 3:
    return None   # cannot build a polygon

poly_4326 = MultiPoint(node_points).convex_hull

# Reproject to EPSG:26916
iso_gdf = gpd.GeoDataFrame({"geometry": [poly_4326]}, crs="EPSG:4326")
iso_gdf = iso_gdf.to_crs("EPSG:26916")
return iso_gdf.geometry.iloc[0]
```

### Running for All Clinics

```python
results_10min = []
results_20min = []

for idx, clinic in clinics_gdf.iterrows():
    try:
        node_id = get_nearest_node(G, clinic.geometry)

        poly_10 = generate_isochrone(G, node_id, 600)
        poly_20 = generate_isochrone(G, node_id, 1200)

        if poly_10 is not None:
            results_10min.append({"clinic": clinic.get("name", str(idx)),
                                   "geometry": poly_10})
        if poly_20 is not None:
            results_20min.append({"clinic": clinic.get("name", str(idx)),
                                   "geometry": poly_20})

        logger.info(f"Clinic {idx+1}/{len(clinics_gdf)}: OK")

    except Exception as e:
        logger.warning(f"Clinic {idx+1} failed: {e}")
        continue

iso_10 = gpd.GeoDataFrame(results_10min, crs="EPSG:26916")
iso_20 = gpd.GeoDataFrame(results_20min, crs="EPSG:26916")
```

### Dissolving Into City-Wide Service Areas

```python
def dissolve_to_union(iso_gdf):
    iso_gdf = iso_gdf.copy()
    iso_gdf["key"] = 1
    dissolved = iso_gdf.dissolve(by="key").reset_index(drop=True)
    dissolved = dissolved[["geometry"]]
    return dissolved

union_10 = dissolve_to_union(iso_10)
union_20 = dissolve_to_union(iso_20)
```

### Performance

Running this for 100 clinics on a 300,000-node graph takes roughly:
- 5–10 minutes on a modern laptop
- Memory usage peaks at ~2–3GB while the graph is loaded

Do not run this inside a Jupyter notebook unless you have 8GB+ RAM.
Run it from the command line via `run_pipeline.py`.

---

## Stage 4: Gap (`pipeline/gap.py`)

**Purpose**: Compute coverage and gap scores per census tract.

**Reads**: `data/processed/stage2/tracts.gpkg`, `data/processed/stage3/isochrones_*.gpkg`

**Writes**: `data/processed/stage4/tracts_scored.gpkg`, `data/processed/stage4/gap_points.gpkg`

### Coverage Fraction

For each census tract, what fraction of its area falls inside the dissolved
isochrone polygon?

```python
def coverage_fraction(tracts_gdf, isochrone_gdf, col_name):
    assert tracts_gdf.crs.to_epsg() == 26916
    assert isochrone_gdf.crs.to_epsg() == 26916

    iso_union = isochrone_gdf.geometry.unary_union

    tracts_gdf = tracts_gdf.copy()
    tracts_gdf[col_name] = tracts_gdf.geometry.apply(
        lambda geom: (
            geom.intersection(iso_union).area / geom.area
            if geom.area > 0 else 0.0
        )
    )
    tracts_gdf[col_name] = tracts_gdf[col_name].clip(0.0, 1.0)
    return tracts_gdf
```

Use spatial index for performance with large isochrone unions:
```python
from shapely.strtree import STRtree

tree = STRtree([iso_union])

def fast_coverage(geom):
    if geom.area == 0:
        return 0.0
    candidates = tree.query(geom)
    if len(candidates) == 0:
        return 0.0
    intersection = geom.intersection(iso_union)
    return min(intersection.area / geom.area, 1.0)
```

### Gap Score

```python
tracts_gdf["gap_score"] = (
    tracts_gdf["population"] * (1.0 - tracts_gdf["coverage_10min"])
).round(2)

tracts_gdf["gap_score_20min"] = (
    tracts_gdf["population"] * (1.0 - tracts_gdf["coverage_20min"])
).round(2)
```

### Top-N Recommended Locations

```python
top_n = tracts_gdf.nlargest(3, "gap_score").copy()
top_n["geometry"] = top_n.geometry.centroid
top_n["rank"] = range(1, 4)
```

Convert centroid coordinates to WGS84 for human-readable output in the brief:
```python
top_n_wgs84 = top_n.to_crs("EPSG:4326")
top_n["lat"] = top_n_wgs84.geometry.y.round(5)
top_n["lon"] = top_n_wgs84.geometry.x.round(5)
```

### Coverage Summary Statistics

```python
total_pop = tracts_gdf["population"].sum()
covered_10 = tracts_gdf[tracts_gdf["coverage_10min"] > 0]["population"].sum()
covered_20 = tracts_gdf[tracts_gdf["coverage_20min"] > 0]["population"].sum()
uncovered  = tracts_gdf[tracts_gdf["coverage_10min"] == 0]["population"].sum()

stats = {
    "total_population": int(total_pop),
    "covered_10min": int(covered_10),
    "covered_20min": int(covered_20),
    "uncovered_10min": int(uncovered),
    "pct_covered_10min": round(covered_10 / total_pop * 100, 1),
    "pct_covered_20min": round(covered_20 / total_pop * 100, 1),
}
logger.info(f"Coverage summary: {stats}")
```

---

## Stage 5: Export (`pipeline/export.py`)

**Two outputs**: GeoPackage and PDF brief.

### GeoPackage Assembly

```python
layers = [
    ("data/processed/stage4/tracts_scored.gpkg",     "tracts_scored"),
    ("data/processed/stage3/isochrones_10min.gpkg",  "isochrones_10min"),
    ("data/processed/stage3/isochrones_20min.gpkg",  "isochrones_20min"),
    ("data/processed/stage2/clinics.gpkg",           "clinics"),
    ("data/processed/stage4/gap_points.gpkg",        "gap_points"),
]

output = "outputs/chicago_accessibility.gpkg"
for i, (src, layer_name) in enumerate(layers):
    gdf = gpd.read_file(src)
    mode = "w" if i == 0 else "a"
    gdf.to_file(output, layer=layer_name, driver="GPKG", mode=mode)
    logger.info(f"Written: {layer_name} ({len(gdf)} features)")
```

### PDF Brief

The brief uses ReportLab's platypus (document layout engine):

```python
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Table,
                                 TableStyle, Spacer, HRFlowable)
from reportlab.lib import colors

doc = SimpleDocTemplate(
    "outputs/brief.pdf",
    pagesize=letter,
    leftMargin=0.75*inch,
    rightMargin=0.75*inch,
    topMargin=1*inch,
    bottomMargin=1*inch,
)

styles = getSampleStyleSheet()
story = []

# Title
story.append(Paragraph("Chicago Urgent Care Accessibility Analysis", styles["Title"]))
story.append(Paragraph("Recommendations for New Clinic Locations", styles["Heading2"]))
story.append(Spacer(1, 0.2*inch))
story.append(HRFlowable(width="100%", thickness=1, color=colors.black))
story.append(Spacer(1, 0.2*inch))

# Coverage summary section
story.append(Paragraph("Coverage Summary", styles["Heading2"]))
summary_data = [
    ["Metric", "Value"],
    ["Total Chicago population", f"{stats['total_population']:,}"],
    ["Population within 10-min drive", f"{stats['covered_10min']:,} ({stats['pct_covered_10min']}%)"],
    ["Population within 20-min drive", f"{stats['covered_20min']:,} ({stats['pct_covered_20min']}%)"],
    ["Population NOT within 10-min drive", f"{stats['uncovered_10min']:,}"],
]
summary_table = Table(summary_data, colWidths=[3.5*inch, 3*inch])
summary_table.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 10),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightyellow]),
]))
story.append(summary_table)
story.append(Spacer(1, 0.2*inch))

# Top 10 underserved tracts table
story.append(Paragraph("Top 10 Most Underserved Census Tracts", styles["Heading2"]))
# ... build table from tracts_gdf.nlargest(10, "gap_score") ...

# Top 3 recommendations
story.append(Paragraph("Top 3 Recommended New Clinic Locations", styles["Heading2"]))
for i, (_, row) in enumerate(top_n.iterrows(), 1):
    story.append(Paragraph(f"Recommendation {i}", styles["Heading3"]))
    story.append(Paragraph(f"Census Tract: {row['NAME']}", styles["Normal"]))
    story.append(Paragraph(f"Coordinates: {row['lat']:.4f}°N, {row['lon']:.4f}°W",
                            styles["Normal"]))
    story.append(Paragraph(f"Population: {int(row['population']):,}", styles["Normal"]))
    story.append(Paragraph(
        f"Current 10-min coverage: {row['coverage_10min']:.1%}",
        styles["Normal"]
    ))
    story.append(Paragraph(f"Gap score: {row['gap_score']:,.0f}", styles["Normal"]))
    story.append(Spacer(1, 0.1*inch))

# Footer / methodology
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
story.append(Spacer(1, 0.1*inch))
story.append(Paragraph(
    "Methodology: Drive-time isochrones computed using OpenStreetMap road network "
    "via OSMnx and NetworkX. Gap score = population × (1 − 10-min coverage fraction). "
    "Data sources: US Census Bureau ACS 2022; City of Chicago Open Data Portal; "
    "OpenStreetMap contributors (ODbL). Analysis date: " + datetime.now().strftime("%B %Y"),
    styles["Normal"]
))

doc.build(story)
```

---

## QGIS Finalisation

After `python run_pipeline.py` completes:

1. Open QGIS → New Project → Set CRS to EPSG:26916
2. Load `outputs/chicago_accessibility.gpkg`
3. Style `tracts_scored`:
   - Graduated symbology on `gap_score`
   - Colour ramp: Blues reversed → Reds (blue = served, red = underserved)
   - 5 classes, Natural Breaks (Jenks)
4. Style `isochrones_10min`: no fill, blue outline, 40% opacity
5. Style `isochrones_20min`: no fill, light blue outline, 20% opacity
6. Style `clinics`: small dark grey circle, size 4
7. Style `gap_points`: red star marker, size 10, label "Recommended"
8. Print Layout:
   - A3 landscape
   - Main map: Chicago extent
   - Inset map: Illinois with Chicago highlighted
   - Title, legend, scale bar, north arrow
   - Source citations bottom right
9. Export PDF + PNG (300 dpi) to `outputs/maps/`

---

## Approximate Runtime

| Stage | Estimated time |
|---|---|
| Stage 1: Ingest | 5–10 min (graph download dominates) |
| Stage 2: Reproject | 30–60 seconds |
| Stage 3: Network | 5–15 min (Dijkstra's for all clinics) |
| Stage 4: Gap | 1–3 min |
| Stage 5: Export | 30–60 seconds |
| **Total** | **~15–30 minutes** |

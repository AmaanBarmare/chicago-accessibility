# Chicago Urgent Care Accessibility Analysis

> A Python-first geospatial pipeline that identifies underserved neighbourhoods
> in Chicago for urgent care clinic expansion using real road-network drive-time
> analysis and population data.

---

## Portfolio Pitch

*"Built a network-based accessibility analysis pipeline in Python using OSMnx and
NetworkX to identify underserved Chicago neighbourhoods for urgent care clinic
placement. Produced a gap-scored map and a one-page business recommendation PDF,
both generated programmatically. QGIS used for final publication-quality cartography."*

---

## What This Project Does

This pipeline downloads 4 open datasets, builds a real road network graph of
Chicago, generates drive-time isochrones from every existing urgent care clinic,
and scores every census tract by how underserved it is relative to its population.

The final outputs are:
- A GeoPackage loaded into QGIS for a styled choropleth map
- A programmatically generated one-page PDF brief with the top 3 recommended
  new clinic locations and data-backed justification

All spatial analysis and PDF generation is written in Python. QGIS is used only
for final map styling and print layout.

---

## The Core Question

**"Which Chicago neighbourhoods have the worst access to urgent care,
and where should the next three clinics be built?"**

---

## How It Works — Plain English

### The Big Idea

You have 4 datasets. You want one number per census tract — a gap score. The
pipeline takes raw data from 4 different internet sources and answers one question:
which Chicago neighbourhoods have the worst access to urgent care, weighted by
how many people live there?

### Why 5 Stages Instead of One Script

If everything were in one script, a failed download halfway through means
restarting from zero. Each stage saves its output to disk. If Stage 4 breaks,
you fix it and rerun only Stage 4. Stages 1–3 already ran and are sitting on
disk. The `--from-stage` flag exists exactly for this.

### Each Stage in Plain English

**Stage 1 — Ingest: "Go get the data"**
Downloads all four datasets and saves raw files to `data/raw/`. Skips any file
that already exists. The Chicago road graph is the largest download — OSMnx
fetches every road segment in the city.

**Stage 2 — Reproject: "Make everything speak the same language"**
Converts every dataset from WGS84 (lat/lon degrees) to EPSG:26916 (UTM Zone 16N,
metres). Clips everything to the Chicago city boundary. After this stage every
layer is in the same coordinate system, same extent, no broken geometries.
No spatial operation happens before this.

**Stage 3 — Network: "Figure out where you can actually drive in 10 and 20 minutes"**
This is what makes this project different from Project 1, which used simple
circular buffers. This stage uses the real road network.

It loads Chicago's road graph — every intersection is a node, every road segment
is an edge. It adds speed (based on road type) and travel time in seconds to
every edge. Then for each existing clinic it runs Dijkstra's algorithm outward,
collecting every node reachable within 600 seconds (10 min) and 1200 seconds
(20 min). Those reachable nodes become a polygon — the isochrone. It dissolves
all clinic isochrones into two union polygons: total 10-minute coverage and
total 20-minute coverage across the city.

**Stage 4 — Gap: "Find the underserved areas"**
Spatially joins the isochrones to census tracts. For each tract, computes what
fraction of its area is covered by the 10-minute service area. Then computes:

```
gap_score = tract_population × (1 − coverage_fraction)
```

A tract with 8,000 people and no clinic coverage scores 8,000. A fully covered
tract scores 0. Tracts are ranked — highest gap score = most underserved. The
top 3 gap clusters become the recommended new clinic locations.

**Stage 5 — Export: "Pack it up and write the brief"**
Assembles all layers into a single GeoPackage. Also programmatically generates
a one-page PDF brief — gap score table, top 3 recommendations with coordinates
and justification, coverage statistics. No manual writing.

### The Whole Thing as One Story

Chicago has 801 census tracts. You want to find which ones are most underserved
by urgent care. You download the road network, build a graph, and calculate real
drive-time coverage from every existing clinic. You compute a gap score per tract
that combines population with lack of coverage. The map shows Chicago in a
cool-to-warm colour scale — blue tracts are well-served, red tracts are
underserved. The PDF brief tells a healthcare executive exactly where to open
the next three clinics and why.

---

## Interview Walkthrough — How To Talk About This Project

This section is written the way you'd actually explain the project in a conversation.
Read it out loud a few times before an interview.

### The One-Line Pitch

"It's a Python pipeline that figures out which Chicago neighbourhoods are the
most underserved by urgent care clinics, and recommends where to build the next
three. It uses real drive-time analysis on the road network, not just circles
on a map."

### The Big Idea

You have four datasets. You want one number for every Chicago neighbourhood — a
gap score. The pipeline pulls raw data from four different sources and answers
one question: which neighbourhoods have the worst access to urgent care,
weighted by how many people actually live there?

Everything is Python. QGIS only touches the final output. The pipeline also
writes a one-page PDF brief automatically — no manual writing at the end.

### The 5 Stages — What Each One Does and Why It Exists

**Stage 1 — Ingest. "Go get the data."**
Downloads the four datasets: census tract boundaries and population, existing
clinic locations from the Chicago Data Portal, the Chicago road network from
OpenStreetMap, and the city boundary. If a file already exists on disk it skips
the download, so you can rerun the pipeline without hammering the APIs. This
stage exists because APIs are slow and flaky — you want the raw data cached
locally once and never have to touch the internet again.

**Stage 2 — Reproject. "Make everything speak the same language."**
Takes every raw file and does three things: converts it from lat/lon degrees
to metres (EPSG:26916), throws out any broken or empty shapes, and clips
everything to the Chicago city boundary. After this stage every layer is in
the same coordinate system, covers the same area, and has clean geometry.
This stage exists because you can't do real distance or area math in degrees —
one degree of longitude in Chicago is not the same length as one degree of
latitude. Metres are metres everywhere.

**Stage 3 — Network. "Figure out where you can actually drive in 10 and 20 minutes."**
This is the core of the project and what makes it different from a basic GIS
assignment. It loads Chicago's road network as a graph — every intersection
is a dot, every road segment is a line connecting two dots. Each line gets
a speed based on the type of road (motorway, residential, etc.) and a travel
time in seconds. Then for every existing clinic, it traces outward through
the road network to find every intersection you could reach within 10 minutes
and within 20 minutes. Those reachable points become a polygon — the isochrone.
Finally it merges all 47 clinic isochrones into one big "total 10-minute
coverage" polygon and one "total 20-minute coverage" polygon. This stage exists
because the whole project only makes sense if the drive-time analysis is real —
using circles instead would defeat the point.

**Stage 4 — Gap. "Find the underserved neighbourhoods."**
For each census tract, it asks: what percentage of your area falls inside the
10-minute coverage polygon? Then it multiplies:

```
gap_score = tract_population × (1 − coverage_fraction)
```

A neighbourhood with 8,000 people and zero coverage scores 8,000. The same
neighbourhood fully covered scores 0. Rank every tract by gap score — the top
three become the recommended clinic locations. This stage exists to turn a
map ("here's where the coverage is") into a ranked list of actionable
recommendations ("here are the three places to build next").

**Stage 5 — Export. "Pack it up and write the brief."**
Two outputs. First, a single GeoPackage file containing every layer — the
thing you open in QGIS to make the final map. Second, a one-page PDF brief
generated automatically using Python's ReportLab library. The brief has the
coverage stats, a top-10 underserved table, and the three recommended
locations with coordinates and justification. This stage exists because a
map alone isn't a deliverable — a non-GIS decision-maker needs something
they can read and act on in two minutes.

### Data Flow in One Line Per Stage

```
Internet APIs         →  data/raw/                                    (Stage 1)
data/raw/             →  data/processed/stage2/   reprojected + clipped    (Stage 2)
stage2/               →  data/processed/stage3/   isochrones (10 + 20 min) (Stage 3)
stage2/ + stage3/     →  data/processed/stage4/   tracts with gap scores   (Stage 4)
stage2/3/4/           →  outputs/ gpkg + brief.pdf                    (Stage 5)
```

### Why 5 Stages Instead of One Script

Stage 1 is the slowest because it's network-dependent — OSMnx downloads the
entire Chicago road graph and that takes a few minutes. Stage 3 is the most
CPU-heavy — running the drive-time algorithm from every clinic across the
whole city takes real time. By splitting them, you can rerun Stage 4 and 5
ten times while tuning the gap scoring logic without re-downloading or
recomputing anything. If one stage breaks, you fix it and rerun just that
stage. Nothing upstream needs to happen again.

### The Role of config.py

Every number in the project lives in one file — travel time thresholds
(600 seconds, 1200 seconds), assumed speeds for each type of road, the
coordinate system, file paths. If someone asks "what does coverage look like
at 15 minutes instead of 10?" you change one number and rerun from Stage 3.
That's the engineering point — no magic numbers buried in the code.

### What QGIS Actually Does

Only one thing: takes the final GeoPackage, styles the census tracts with a
cool-to-warm colour ramp on gap score (blue = well-served, red = underserved),
overlays the isochrones as transparent fills, marks the three recommended
locations with symbols, and produces a print layout with a main map and a
small inset map showing where Chicago sits in Illinois. All the analysis is
already done in Python before QGIS opens. QGIS is the publishing tool, not
the analysis tool.

---

## The Core Concept — Isochrones vs Buffers

This is the single most important idea in the project. It's also the easiest
thing to explain in an interview because anyone can picture it.

**Buffers are circles.** If you draw a 1km circle around a clinic, you're saying
"everyone inside this circle has access." That ignores rivers, railways,
highways, dead-end streets, and every other real obstacle. It's fast and it
works for a first-pass analysis, but it's not how people actually get to a
clinic.

**Isochrones are drive-time polygons.** An isochrone answers a different
question: "where can you actually drive to from this clinic in 10 minutes?"
It follows the road network. It respects speed limits. The resulting polygon
is irregular — long and narrow along highways, short and rounded in dense
grid neighbourhoods. It looks like a real catchment area because it is one.

Here's what Stage 3 does, step by step:

```
Chicago road network (from OpenStreetMap)
    ↓
Add a speed (km/h) to every road segment, based on road type
    ↓
Convert speed → travel time in seconds per segment
    ↓
For each existing clinic:
    → find the nearest intersection on the graph
    → trace outward along the roads, adding up travel time
    → stop at every intersection reachable within 600 seconds (10 min)
    → connect those points into a polygon — that's the isochrone
    → repeat for 1200 seconds (20 min)
    ↓
Merge all clinic isochrones into two union polygons
(one showing 10-min city-wide coverage, one showing 20-min)
```

**Why this matters for the project.** A clinic two blocks from I-90 might have
a 10-minute isochrone stretching five miles along the highway. A clinic in a
dense residential grid might have a 10-minute isochrone that's only a mile
across. Buffers treat them as identical. Isochrones show the truth. For a
real infrastructure decision — where to spend millions on a new clinic —
that difference is the entire point.

---

## Why Chicago

Three reasons, all portfolio-driven.

**1. Geographic variety.** A portfolio with two projects on the same city shows
one city and one data ecosystem. Two different cities — Chicago and Philadelphia —
signals that you can work with any municipal open data portal, not just the
one you already know. It also covers two distinct urban contexts (Midwest and
Northeast).

**2. Chicago's open data portal is one of the best in the US.** The Chicago
Data Portal is consistently ranked among the top municipal open data platforms
in the country. Clean datasets, stable APIs, good coverage of health facilities.
For a project that depends on finding existing clinic locations, that matters —
many cities don't publish this data cleanly, or at all.

**3. The problem fits Chicago's geography.** Chicago is a large, sprawling
city with well-documented neighbourhood-level inequality in healthcare access.
The South Side and West Side have real, measurable gaps compared to the North
Side and downtown. This means the gap analysis will find genuine, meaningful
gaps — the map tells an interesting story. Run the same analysis on a small,
compact city and everything comes out covered, which makes for a boring map
and a pointless recommendation.

---

## Tech Stack

| Tool | Role |
|---|---|
| Python 3.11+ | All analysis and pipeline logic |
| GeoPandas | Spatial data manipulation |
| OSMnx | Download Chicago road network as a graph |
| NetworkX | Dijkstra's algorithm for drive-time calculations |
| Shapely | Geometry operations (isochrone polygon construction) |
| Pandas | Tabular data wrangling |
| Requests | Census API + Chicago Data Portal API calls |
| PyProj | CRS transformations |
| Fiona | GeoPackage read/write |
| ReportLab | Programmatic PDF brief generation |
| Matplotlib / Contextily | Quick visual checks during development |
| QGIS | Final map styling and print layout only |

---

## Project Structure

```
chicago-accessibility/
│
├── README.md                  ← you are here
├── CLAUDE.md                  ← instructions for Claude Code
├── ARCHITECTURE.md            ← full pipeline design decisions
├── DATA_SOURCES.md            ← every data source with URLs and field specs
├── PIPELINE.md                ← stage-by-stage implementation guide
│
├── config.py                  ← all constants: thresholds, CRS, paths, speeds
│
├── pipeline/
│   ├── __init__.py
│   ├── ingest.py              ← Stage 1: download and save raw data
│   ├── reproject.py           ← Stage 2: reproject, validate, clip
│   ├── network.py             ← Stage 3: build graph, generate isochrones
│   ├── gap.py                 ← Stage 4: coverage join, gap scoring
│   └── export.py              ← Stage 5: GeoPackage + PDF brief
│
├── run_pipeline.py            ← single entry point, runs all 5 stages
│
├── data/
│   ├── raw/                   ← downloaded files, never modified after download
│   │   ├── census/
│   │   ├── clinics/
│   │   ├── network/
│   │   └── boundary/
│   └── processed/             ← outputs from each pipeline stage
│       ├── stage2/
│       ├── stage3/
│       └── stage4/
│
├── outputs/
│   ├── chicago_accessibility.gpkg   ← final scored layer for QGIS
│   ├── brief.pdf                    ← one-page recommendation brief
│   └── maps/                        ← exported map images from QGIS
│
└── notebooks/
    ├── 01_explore_census.ipynb
    ├── 02_explore_clinics.ipynb
    ├── 03_explore_network.ipynb
    └── 04_gap_experiments.ipynb
```

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/yourname/chicago-accessibility.git
cd chicago-accessibility
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set environment variables

```bash
cp .env.example .env
# Edit .env and add your CENSUS_API_KEY
```

### 5. Create required directories

```bash
python run_pipeline.py --setup
```

---

## Running the Pipeline

### Run all stages end-to-end

```bash
python run_pipeline.py
```

### Run a single stage

```bash
python run_pipeline.py --stage ingest
python run_pipeline.py --stage reproject
python run_pipeline.py --stage network
python run_pipeline.py --stage gap
python run_pipeline.py --stage export
```

### Run from a specific stage onwards

```bash
python run_pipeline.py --from-stage network
```

Most useful during development — Stage 3 (network) takes the longest to compute.
Once isochrones are generated in `data/processed/stage3/`, rerun gap and export
as many times as needed without recomputing them.

---

## Output Files

### `outputs/chicago_accessibility.gpkg`

| Layer | Description |
|---|---|
| `tracts_scored` | All Chicago census tracts with population + gap score |
| `isochrones_10min` | Union of all 10-minute drive polygons from existing clinics |
| `isochrones_20min` | Union of all 20-minute drive polygons |
| `clinics` | Existing urgent care clinic point locations |
| `gap_points` | Top 3 recommended new clinic locations |

### `outputs/brief.pdf`

A one-page business brief containing:
- Coverage statistics: population within 10 and 20 minutes of existing clinics
- Top 10 most underserved tracts (gap score table)
- Top 3 recommended new clinic locations with coordinates and justification
- Methodology note

---

## Requirements

```
geopandas>=0.14.0
osmnx>=1.9.0
networkx>=3.2.0
shapely>=2.0.0
pandas>=2.0.0
requests>=2.31.0
pyproj>=3.6.0
fiona>=1.9.0
reportlab>=4.0.0
matplotlib>=3.8.0
contextily>=1.4.0
python-dotenv>=1.0.0
pygris>=0.1.6
```

---

## Data Sources

All data is free and openly licensed. See `DATA_SOURCES.md` for full details.

| Dataset | Source | Licence |
|---|---|---|
| Census tracts + population | US Census Bureau ACS | Public domain |
| Urgent care clinics | Chicago Data Portal | Open data |
| Road network | OpenStreetMap via OSMnx | ODbL |
| City boundary | US Census Bureau TIGER | Public domain |

---

## What Makes This Different From a Basic GIS Project

Most GIS accessibility analyses use simple circular buffers — draw a 1km circle
around each facility and call everything inside it "served". This pipeline uses
actual drive-time isochrones computed on the real road network. A clinic next to
a highway has a dramatically larger 10-minute service area than a clinic in a
dense grid neighbourhood. The difference matters when making real infrastructure
decisions.

The programmatic PDF brief is the second differentiator. The map answers "where
are the gaps?" The brief answers "what should we do about it?" — which is what
decision-makers actually need.

---

## Skills Demonstrated

- Network-based geospatial analysis (OSMnx + NetworkX)
- Drive-time isochrone generation from real road graphs
- Dijkstra's algorithm applied to spatial problems
- Population-weighted gap scoring
- CRS management (EPSG:26916 UTM Zone 16N)
- Modular Python pipeline engineering
- Programmatic PDF report generation (ReportLab)
- Publication-quality QGIS cartography

---

## Licence

MIT

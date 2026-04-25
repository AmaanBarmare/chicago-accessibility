# Chicago Healthcare Accessibility Analysis

> A Python-first geospatial pipeline that identifies underserved neighbourhoods
> in Chicago for public and community health clinic expansion using real road-network
> drive-time analysis and population data.

---

## Portfolio Pitch

*"Built a network-based accessibility analysis pipeline in Python using OSMnx and
NetworkX to identify underserved Chicago neighbourhoods for public and community
health clinic placement. Produced a gap-scored map and a one-page business
recommendation PDF, both generated programmatically. QGIS used for final
publication-quality cartography."*

---

## What This Project Does

This pipeline downloads 4 open datasets, builds a real road network graph of
Chicago, generates drive-time isochrones from every existing public and community
health clinic, and scores every census tract by how underserved it is relative to
its population.

The final outputs are:
- A GeoPackage loaded into QGIS for a styled choropleth map
- A programmatically generated one-page PDF brief with the top 3 recommended
  new clinic locations and data-backed justification

All spatial analysis and PDF generation is written in Python. QGIS is used only
for final map styling and print layout.

---

## The Core Question

**"Which Chicago neighbourhoods have the worst access to public and community
health clinics, and where should the next three clinics be built?"**

---

## How It Works — Plain English

### The Big Idea

You have 4 datasets. You want one number per census tract — a gap score. The
pipeline takes raw data from 4 different internet sources and answers one question:
which Chicago neighbourhoods have the worst access to public and community health
clinics, weighted by how many people live there?

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
by public and community health clinics. You download the road network, build a
graph, and calculate real drive-time coverage from every existing clinic. You compute a gap score per tract
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
most underserved by public and community health clinics, and recommends where
to build the next three. It uses real drive-time analysis on the road network,
not just circles on a map."

### The Big Idea

You have four datasets. You want one number for every Chicago neighbourhood — a
gap score. The pipeline pulls raw data from four different sources and answers
one question: which neighbourhoods have the worst access to public and community
health clinics, weighted by how many people actually live there?

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
Finally it merges all the per-clinic isochrones into one big "total 10-minute
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

## Challenges Faced

These are the things that didn't go to plan during implementation. They're the
most interesting parts to talk about in an interview — every one is an example
of "the documents lied, look at the actual data."

### 1. The documented Chicago Data Portal dataset IDs were wrong

The Chicago Data Portal exposes datasets by short alphanumeric IDs (like
`iqnk-2tcu`). The reference docs pointed at two specific clinic datasets by ID.
The first one, when actually queried, returned epidemiological *rates per
community area* — birth rates, cancer rates, lead poisoning rates — with no
clinic locations at all. The second one was a 404; the dataset had been
removed. The whole project would have silently produced an empty map if I'd
trusted the docs.

What saved it was a defensive logging rule: **before parsing any API response,
log its actual columns and a sample record.** That made the mismatch visible
on the first run. From there I queried the Chicago Data Portal's catalog API
with `q=health clinic` to find the real, currently-live datasets — `kcki-hnch`
(CDPH clinic locations, 24 sites) and `cjg8-dbka` (Primary Care Community
Health Centers, 120 sites). Combined and de-duplicated by coordinate to 139
total facilities.

The interview takeaway: live APIs drift. Field names change between versions,
datasets get deprecated and replaced, response shapes don't match the docs.
The defensive habit of *logging what you got before parsing it* is what turns
a silent failure into a fixable one.

### 2. `gpd.clip` produced 71 invisible "ghost" tracts

Stage 2 clips Cook County tracts to the Chicago city boundary. The standard
geometry-validation pattern — drop nulls, drop empties, drop invalids — let
through 71 tracts that had been clipped down to zero-area `MultiLineString`
and `Point` geometries. These were Cook County suburbs whose tract polygons
happened to share a small boundary segment with Chicago; the clip operation
reduced their geometry to that shared line.

These ghosts were technically valid geometries (not empty, not null, not
invalid) but had `area = 0`. They inflated Chicago's "population" total to
3.08 million — about 15% above the real number — because the population value
was kept even though the geometry was meaningless. They would also have
caused division-by-zero in Stage 4's coverage-fraction calculation.

The fix was a one-line filter: after every clip, keep only `Polygon` and
`MultiPolygon` geometries (or `Point`/`MultiPoint` for the clinics layer).
After that, Chicago's population dropped to 2,665,636 — matching ACS 2022
estimates almost exactly.

The interview takeaway: "valid" is a low bar. Geometry validation has to
include "is this the *type* of geometry I expected?", not just "is it
well-formed?".

### 3. OSMnx v2's road graph is ten times smaller than the docs assumed

The reference docs estimated Chicago's drive-network graph would have
200,000–400,000 nodes and 500,000–900,000 edges. The actual graph came in at
**29,621 nodes and 77,709 edges** — about a tenth of the predicted size.

The reason is that OSMnx v2 defaults to `simplify=True`, which collapses
chains of degree-2 intermediate nodes into single edges (a long straight
street becomes one edge instead of dozens). The total road network is
identical — segment lengths and travel times are preserved — but the graph
representation is much smaller. Stage 3, which the docs warned might take
5–15 minutes of CPU time, completed in 93 seconds.

The interview takeaway: when something runs much faster than expected, that's
a signal to *verify* it actually did the work, not just declare victory. I
round-tripped the graph to disk and back to confirm `travel_time` and
`length` were preserved, then sanity-checked one clinic's isochrone polygon
shape before running the full loop of 138.

### 4. OSMnx v2 added a hidden dependency on scikit-learn

When I called `ox.nearest_nodes()` to find the closest graph node to each
clinic, it raised `ImportError: scikit-learn must be installed as an optional
dependency to search an unprojected graph`. The original docs and the v1
OSMnx API didn't require it. v2 uses scikit-learn's `BallTree` for
nearest-neighbour search on lat/lon graphs.

Easy fix — `pip install scikit-learn`, add it to `requirements.txt` — but
worth flagging because it's the kind of "the library you depend on quietly
grew a new dependency between major versions" issue that breaks
reproducibility for anyone else cloning the repo.

### 5. Field names and CRSes weren't quite what the docs said

A handful of small mismatches that didn't break anything but each took a
moment to debug:

- The docs predicted Census tracts would have columns named `AREALAND` and
  `AREAWATER`. The TIGER 2020 vintage actually uses `ALAND` and `AWATER`.
  A defensive column filter (`[c for c in keep if c in tracts.columns]`)
  caught this without crashing.
- The docs said tracts would arrive in EPSG:4326 (WGS84). pygris natively
  returns EPSG:4269 (NAD83). For Chicago the difference is sub-metre, and
  `to_crs(...)` reprojects either correctly, but the assertion in my smoke
  test had to be loosened.
- The Chicago boundary area was predicted at ~589 km². TIGER's 2024
  "places" polygon includes water and shoreline, so the actual reprojected
  area is 607 km². The sanity-check range I'd written (500–700 km²) caught
  this without raising an error.

The interview takeaway: when you're integrating five different open-data
sources, every one of them has small surprises. Assertions and sanity ranges
that *log* rather than *crash* are the difference between "I noticed and
adjusted" and "the pipeline died at 2am".

### 6. Convex-hull isochrones overestimate coverage near the lake and city edges

The choice to build isochrone polygons as the convex hull of reachable graph
nodes is a known simplification (alpha shapes would be more accurate but
require tuning a concavity parameter per city). What I didn't fully appreciate
going in was how much it would inflate the *raw* coverage numbers: the
dissolved 10-minute union came out at 643 km² — 106% of Chicago's land area —
because the hulls extend out into Lake Michigan and into the surrounding Cook
County suburbs.

The fix was to clip the isochrone union to the Chicago boundary before
computing per-tract coverage fractions. After that, real Chicago-only
coverage came in at 91.6% at 10 minutes and 94.0% at 20 minutes — leaving a
meaningful 8.4% uncovered zone (about 51 km²) for the gap analysis to score.
I documented the convex-hull simplification as a scope note in the PDF brief
rather than switching to alpha shapes mid-flight.

The interview takeaway: when an analytical method has a known accuracy
ceiling, surface it in the deliverable. Don't pretend the result is more
precise than the method allows.

### 7. The clinic dataset shapes the result, not just the geography

The Chicago Data Portal cleanly publishes CDPH-run public clinics and
federally-funded community health centers. It does not cleanly publish
commercial walk-in clinics (hospital-affiliated urgent cares, retail
pharmacy clinics, private practices). That choice of dataset directly
shapes where the gap analysis finds gaps: public and community health
clinics are deliberately concentrated on the South and West Side because
that's where the population health need is documented, so those areas come
out *well-served* by this dataset. The Northwest Side relies on commercial
walk-in clinics that aren't in the data, so it shows up as the biggest gap
in the analysis.

That's a real, true result for the question "where are the gaps in *public
and community health clinic* coverage?" — but it would be misleading to
present it as "where are the gaps in healthcare access overall". The PDF
brief surfaces this explicitly as a scope caveat under the recommendations
table.

The interview takeaway: every analysis is shaped by the data you have, not
the data you wish you had. Make the scope of the question match the scope
of the data, and call out that boundary in the deliverable.

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
| `clinics` | Existing public and community health clinic point locations |
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
| Public + community health clinics | Chicago Data Portal | Open data |
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

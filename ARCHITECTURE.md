# ARCHITECTURE.md — Design Decisions

This document explains every design decision in the pipeline. Read this if you
want to understand why things are built the way they are, not just what to build.

---

## Overview

The pipeline is a linear 5-stage system. Each stage has a single public `run()`
function. Stages are decoupled — each can run independently as long as its
input files exist.

```
ingest.py → reproject.py → network.py → gap.py → export.py
   ↓              ↓             ↓           ↓          ↓
data/raw/    stage2/*.gpkg  stage3/*.gpkg  stage4/  outputs/
```

---

## Why EPSG:26916 (UTM Zone 16N)?

Chicago sits in UTM Zone 16N. This is the standard projected CRS for spatial
analysis in the Chicago/Illinois region.

**Why not EPSG:4326 (WGS84)?**
WGS84 is geographic (degrees), not projected (metres). A 600-second isochrone
requires measuring distances along road edges in real-world units. Degrees are
meaningless for this — they vary in distance depending on latitude. Everything
that involves distance or area must use a projected CRS.

**Why not Illinois State Plane?**
Illinois State Plane East (EPSG:3435) is also valid for Chicago and is used
by the City of Chicago for official spatial data. However, UTM Zone 16N is more
widely used in open-source geospatial tools, has better global library support,
and produces less confusion when sharing data. Either is technically correct.

**Units: metres.** All buffer distances, area calculations, and travel time
conversions use metres.

---

## Why Isochrones Instead of Circular Buffers?

This is the most important design decision and the one that makes this project
technically stronger than a basic accessibility analysis.

**Circular buffers (the naive approach):**
Draw a 1km circle around each clinic. Call everything inside it "served".
Problems:
- A 1km circle crosses rivers, railways, and highways without a bridge.
  In reality you cannot drive there.
- A clinic next to I-90 has a 10-minute drive area 5x larger than a clinic
  in a dense residential grid. Buffers give them the same area.
- Buffers are symmetric — real accessibility is not. Driving north on a
  one-way street is different from driving south.

**Drive-time isochrones (this approach):**
From each clinic, run Dijkstra's algorithm on the road graph. Find every
intersection reachable within 600 seconds. Build a polygon from those
intersections. This polygon reflects real road network topology, speed limits,
and connectivity. A clinic next to a motorway gets a much larger polygon.
A clinic blocked by the Chicago River to the east gets a polygon that respects
that constraint.

**The trade-off:**
Isochrones take longer to compute. On a city-scale graph, running Dijkstra's
from every clinic takes 5–15 minutes of CPU time vs seconds for buffers.
The pipeline is designed to make this a one-time computation (Stage 3 output
is saved to disk and never recomputed unless explicitly requested).

---

## Why Convex Hull for Isochrone Polygons?

After collecting all reachable nodes, the pipeline builds a convex hull from
their coordinates. This is a simplification.

**The accurate approach is alpha shapes (concave hulls).** These produce
polygons that can be non-convex — they follow the actual shape of the road
network, including "holes" where parks, industrial areas, or water bodies have
no roads.

**Why convex hull instead:**
- Alpha shapes require the `alphashape` library and a tuning parameter (α)
  that needs manual calibration per city
- Alpha shapes are 10–30x slower to compute than convex hulls
- For a portfolio analysis, convex hull is a well-understood, defensible choice
- When presenting, note the simplification and explain that alpha shapes would
  improve accuracy

**Implication:** Convex hull isochrones will slightly overestimate coverage in
areas with geographic barriers (Lake Michigan coastline, river corridors,
large parks). This means the gap analysis is slightly conservative — areas
near Lake Michigan may be counted as "covered" when they're actually not
driveable from the clinic.

---

## Why Population-Weighted Gap Scoring?

The gap score formula is:
```
gap_score = population × (1 − coverage_fraction)
```

**Why not just rank by coverage fraction (% uncovered)?**
A census tract with 100 people and 0% coverage has a coverage fraction of 1.0
(fully uncovered). A tract with 10,000 people and 20% uncovered has a coverage
fraction of 0.2. Ranking by coverage fraction alone would prioritise the
100-person tract over the 10,000-person tract. That is the wrong answer from
a public health resource allocation perspective.

**Why population-weighted:**
The gap score captures unmet need — how many person-minutes of healthcare
access are missing. A tract with high population and low coverage represents
more total unmet need than a sparsely populated uncovered tract. This is
consistent with standard health equity methodology.

**Why 10-minute threshold as primary:**
- 10 minutes is the clinical standard for "urgent" care access in US health
  policy research (see HRSA shortage area designations)
- 20 minutes is the secondary threshold used for context
- Using both gives the brief a richer narrative: "X% of the population is
  within 10 minutes; Y% within 20 minutes"

---

## Why Chicago for This Analysis?

Three reasons:

1. **Open data quality.** The Chicago Data Portal has clean, documented,
   stable health facility data with accurate coordinates. Many other cities
   do not publish this clearly.

2. **Geographic interest.** Chicago has well-documented healthcare access
   disparities between the South/West Side and North Side/downtown. The gap
   analysis will find real, meaningful results — not a uniform coverage map.

3. **Portfolio variety.** Project 1 uses Philadelphia. Two different cities
   signals adaptability to any open data ecosystem.

---

## Why a Programmatic PDF Brief?

Most GIS portfolio projects end with a map. This one ends with a map and
a written recommendation brief generated entirely in Python.

**The brief matters because:**
- Maps answer "where are the gaps?"
- Briefs answer "what should we do?" — which is what decision-makers need
- Generating the brief in Python (not Word or manually) shows that the
  pipeline produces a complete, reproducible deliverable
- It demonstrates that you understand the business context, not just the
  spatial analysis

**ReportLab was chosen because:**
- It is pure Python, no external dependencies beyond pip
- It produces actual PDF, not HTML-rendered-to-PDF
- It is the standard for programmatic PDF generation in Python
- Alternative: `fpdf2` is simpler but less powerful for tables

---

## Why Cook County for Census Data?

The Census TIGER API organises tracts by county, not by city. Chicago lies
within Cook County (FIPS 17031). Downloading all Cook County tracts and
clipping to the Chicago city boundary is the standard approach.

Cook County includes many Chicago suburbs (Evanston, Oak Park, Cicero).
These are removed by the city boundary clip in Stage 2.

Expected tract counts:
- Cook County total: ~1,300 tracts
- Chicago proper after clip: ~800 tracts

---

## Data Flow Diagram

```
SOURCES              STAGE 1       STAGE 2           STAGE 3
                     ingest.py     reproject.py       network.py

Census TIGER  ──────→ tracts ──────→ tracts.gpkg ───→  (used as base)
Census ACS   ───────→ population ──→ (joined to tracts)
Chicago Portal ─────→ clinics ─────→ clinics.gpkg ──→  isochrones
                                                         (10min + 20min)
OSMnx ──────────────→ graph.graphml→ (not reprojected)→ graph loaded here
pygris ──────────────→ boundary ───→ boundary.gpkg ──→  (clip mask)

              STAGE 4            STAGE 5
              gap.py             export.py

              coverage_10min ──→ chicago_accessibility.gpkg
              coverage_20min      ├─ tracts_scored
              gap_score           ├─ isochrones_10min
              gap_points          ├─ isochrones_20min
                                  ├─ clinics
                                  └─ gap_points
                               brief.pdf
                                  ├─ coverage stats
                                  ├─ top 10 gap table
                                  └─ top 3 recommendations
```

---

## Modular Design Rationale

Same reasoning as Project 1 — but with one additional benefit specific to
this project: **Stage 3 is extremely expensive.**

Running Dijkstra's algorithm from 50–200 clinics across a 300,000+ node
road graph takes 5–15 minutes of CPU time. The modular design means this
computation runs exactly once. When you want to adjust the gap scoring
formula (Stage 4) or the PDF layout (Stage 5), you rerun only those stages
without touching the isochrone computation.

The `--from-stage network` flag exists precisely for cases where you need to
re-run isochrone generation (e.g. after adding more clinic locations) without
re-downloading all the raw data.

---

## Limitations and Known Simplifications

Document these when presenting. They show analytical maturity.

1. **Convex hull isochrones.** As described above, these overestimate coverage
   near geographic barriers. Alpha shapes would be more accurate.

2. **Drive-time only.** The pipeline models car access only. Chicago has
   excellent public transit. A complete analysis would model walk + transit
   access, which is more relevant for low-income populations who may not have
   cars. OSMnx supports `network_type="walk"` and `"bike"` for extensions.

3. **Clinic dataset completeness.** The Chicago Data Portal may not include
   all urgent care facilities — some private operators may not be registered.
   The gap analysis is only as good as the clinic dataset.

4. **Static snapshot.** The analysis uses point-in-time data. Clinics open and
   close, populations shift. A production system would monitor these changes.

5. **Equal population weight.** The gap score weights all residents equally.
   A more sophisticated analysis would weight by demographics most likely to
   use urgent care (elderly, uninsured, households without a primary care
   provider).

6. **Centroid as recommended location.** The top-3 recommended locations are
   the centroids of the most underserved tracts. A real siting analysis would
   also consider zoning, available commercial space, land cost, and proximity
   to public transit.

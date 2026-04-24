# config.py
# All constants for the Chicago Accessibility Pipeline.
# Every magic number in this project comes from here.
# If you change the CRS or travel time thresholds, update dependent values.

import os

# ---------------------------------------------------------------------------
# Coordinate Reference Systems
# ---------------------------------------------------------------------------

PROJECT_CRS  = "EPSG:26916"    # WGS 84 / UTM Zone 16N (metres)
                                # All spatial operations use this CRS.
                                # Units: metres.

DOWNLOAD_CRS = "EPSG:4326"     # WGS84, used only for raw downloads.
                                # All data is reprojected to PROJECT_CRS in Stage 2.
                                # NOTE: OSMnx graph nodes are stored in EPSG:4326
                                # internally. Do not reproject the graph itself.

# ---------------------------------------------------------------------------
# Travel Time Thresholds
# ---------------------------------------------------------------------------

TRAVEL_TIME_10MIN = 600        # 10 minutes in seconds (primary threshold)
TRAVEL_TIME_20MIN = 1200       # 20 minutes in seconds (secondary threshold)

TRAVEL_TIMES = [TRAVEL_TIME_10MIN, TRAVEL_TIME_20MIN]

# The primary threshold used for gap scoring.
# Change to TRAVEL_TIME_20MIN to use 20-min access as the primary metric.
PRIMARY_TRAVEL_TIME = TRAVEL_TIME_10MIN

# ---------------------------------------------------------------------------
# Road Speed Assumptions (km/h)
# Applied to OSM highway tags by ox.add_edge_speeds()
# Based on conservative urban driving conditions in Chicago.
# ---------------------------------------------------------------------------

ROAD_SPEEDS = {
    "motorway":       100,    # Chicago expressways (I-90, I-94, I-290)
    "motorway_link":   60,    # Motorway on/off ramps
    "trunk":           80,    # Major arterials (Lake Shore Drive, Cicero Ave)
    "trunk_link":      50,    # Trunk road ramps
    "primary":         50,    # Major city streets (Michigan Ave, Western Ave)
    "primary_link":    40,    # Primary road links
    "secondary":       40,    # Secondary arterials (Clark St, Halsted St)
    "secondary_link":  30,    # Secondary road links
    "tertiary":        30,    # Neighbourhood through-streets
    "tertiary_link":   25,    # Tertiary road links
    "residential":     25,    # Residential grid streets
    "living_street":   15,    # Pedestrian-priority streets
    "unclassified":    25,    # Roads without explicit classification
    "road":            25,    # Generic road type
    "service":         15,    # Service roads, alleys, parking aisles
}

DEFAULT_SPEED = 25            # km/h fallback for any highway type not in ROAD_SPEEDS

# ---------------------------------------------------------------------------
# Chicago / Illinois FIPS Codes
# ---------------------------------------------------------------------------

STATE_FIPS   = "17"           # Illinois
COUNTY_FIPS  = "031"          # Cook County
COUNTY_FULL  = "17031"        # Combined state + county

# ---------------------------------------------------------------------------
# Chicago OSMnx Parameters
# ---------------------------------------------------------------------------

CHICAGO_PLACE  = "Chicago, Illinois, USA"
NETWORK_TYPE   = "drive"       # Download only driveable roads
OSM_TIMEOUT    = 300           # seconds — allow long downloads for large city

# ---------------------------------------------------------------------------
# Gap Scoring
# ---------------------------------------------------------------------------

TOP_N_RECOMMENDATIONS = 3     # Number of recommended clinic locations to output

# Gap score formula:
#   gap_score = population × (1 − coverage_fraction_at_PRIMARY_TRAVEL_TIME)
# A tract with 8,000 people and 0% coverage → gap_score = 8,000
# A tract with 8,000 people and 100% coverage → gap_score = 0

# ---------------------------------------------------------------------------
# Census API
# ---------------------------------------------------------------------------

CENSUS_ACS_YEAR   = "2022"
CENSUS_POP_TABLE  = "B01003_001E"   # Total population
CENSUS_API_BASE   = "https://api.census.gov/data"
CENSUS_API_KEY    = os.getenv("CENSUS_API_KEY", "")

# ---------------------------------------------------------------------------
# Chicago Data Portal
# ---------------------------------------------------------------------------

CHICAGO_PORTAL_BASE    = "https://data.cityofchicago.org/resource"

# Clinic datasets — verified live 2026-04-24.
# The documentation-listed iqnk-2tcu returns epidemiological rates (no clinics),
# and f5ex-mxwn is a dead 404. The two real, current sources are:
#   kcki-hnch  — CDPH Clinic Locations (city-run; ~24 sites, top-level lat/lon)
#   cjg8-dbka  — Primary Care Community Health Centers (~120; lat/lon nested
#                 inside a location_1 dict)
# Combined these give ~140+ facilities, within the 50-200 expected range.
CLINICS_CDPH_ID             = "kcki-hnch"
CLINICS_COMMUNITY_CENTERS_ID = "cjg8-dbka"
CLINICS_PAGE_LIMIT          = 5000

# ---------------------------------------------------------------------------
# File Paths — Raw Data
# ---------------------------------------------------------------------------

DATA_RAW        = "data/raw"
DATA_PROCESSED  = "data/processed"
OUTPUTS         = "outputs"

RAW_CENSUS      = "data/raw/census"
RAW_CLINICS     = "data/raw/clinics"
RAW_NETWORK     = "data/raw/network"
RAW_BOUNDARY    = "data/raw/boundary"

TRACTS_RAW      = "data/raw/census/tracts.geojson"
POPULATION_RAW  = "data/raw/census/population.csv"
CLINICS_RAW     = "data/raw/clinics/urgent_care.geojson"
GRAPH_RAW       = "data/raw/network/chicago_drive.graphml"
BOUNDARY_RAW    = "data/raw/boundary/chicago_boundary.geojson"

# ---------------------------------------------------------------------------
# File Paths — Processed (Stage 2)
# ---------------------------------------------------------------------------

PROCESSED_S2    = "data/processed/stage2"

TRACTS_S2       = "data/processed/stage2/tracts.gpkg"
CLINICS_S2      = "data/processed/stage2/clinics.gpkg"
BOUNDARY_S2     = "data/processed/stage2/chicago_boundary.gpkg"

# ---------------------------------------------------------------------------
# File Paths — Processed (Stage 3)
# ---------------------------------------------------------------------------

PROCESSED_S3           = "data/processed/stage3"

ISO_10MIN_S3           = "data/processed/stage3/isochrones_10min.gpkg"
ISO_20MIN_S3           = "data/processed/stage3/isochrones_20min.gpkg"
ISO_10MIN_IND_S3       = "data/processed/stage3/isochrones_10min_individual.gpkg"
ISO_20MIN_IND_S3       = "data/processed/stage3/isochrones_20min_individual.gpkg"

# ---------------------------------------------------------------------------
# File Paths — Processed (Stage 4)
# ---------------------------------------------------------------------------

PROCESSED_S4    = "data/processed/stage4"

TRACTS_S4       = "data/processed/stage4/tracts_scored.gpkg"
GAP_POINTS_S4   = "data/processed/stage4/gap_points.gpkg"

# ---------------------------------------------------------------------------
# Output Files
# ---------------------------------------------------------------------------

FINAL_GPKG      = "outputs/chicago_accessibility.gpkg"
BRIEF_PDF       = "outputs/brief.pdf"
MAPS_DIR        = "outputs/maps"

# ---------------------------------------------------------------------------
# GeoPackage Layer Names
# ---------------------------------------------------------------------------

GPKG_TRACTS      = "tracts_scored"
GPKG_ISO_10      = "isochrones_10min"
GPKG_ISO_20      = "isochrones_20min"
GPKG_CLINICS     = "clinics"
GPKG_GAP_POINTS  = "gap_points"

# ---------------------------------------------------------------------------
# All Directories to Create on Setup
# ---------------------------------------------------------------------------

ALL_DIRS = [
    RAW_CENSUS,
    RAW_CLINICS,
    RAW_NETWORK,
    RAW_BOUNDARY,
    PROCESSED_S2,
    PROCESSED_S3,
    PROCESSED_S4,
    OUTPUTS,
    MAPS_DIR,
]

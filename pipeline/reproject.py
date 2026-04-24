"""Stage 2: Reproject.

Reprojects raw data to EPSG:26916, validates geometries, and clips to the
Chicago city boundary. Reads from data/raw/ and writes to data/processed/stage2/.
"""

import logging

import config
from pipeline._common import should_skip

logger = logging.getLogger(__name__)


def _assert_project_crs(gdf, label: str) -> None:
    epsg = gdf.crs.to_epsg() if gdf.crs is not None else None
    if epsg != 26916:
        raise ValueError(f"{label}: expected EPSG:26916, got {gdf.crs}")


def _clean_geometry(gdf, geom_types=None):
    """Drop null/empty/invalid geometries. If geom_types is given
    (e.g. {'Polygon', 'MultiPolygon'}), also drop any geometry not in that set.
    This is needed after gpd.clip, which can produce degenerate
    LineString/Point slivers when a polygon barely touches the clip mask."""
    before = len(gdf)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty & gdf.geometry.is_valid]
    if geom_types is not None:
        gdf = gdf[gdf.geometry.geom_type.isin(geom_types)]
    after = len(gdf)
    if before != after:
        logger.info(f"  dropped {before - after} invalid/null/empty/wrong-type geometries ({before} → {after})")
    return gdf


def process_boundary():
    """Load, reproject, validate, save Chicago boundary. Returns the GDF."""
    import geopandas as gpd

    out = config.BOUNDARY_S2
    if should_skip(out, force=False):
        return gpd.read_file(out)

    logger.info(f"load  {config.BOUNDARY_RAW}")
    boundary = gpd.read_file(config.BOUNDARY_RAW)
    logger.info(f"  raw: {len(boundary)} features, CRS={boundary.crs}")

    boundary = boundary.to_crs(config.PROJECT_CRS)
    boundary = _clean_geometry(boundary)
    _assert_project_crs(boundary, "boundary")

    area_sqm = float(boundary.geometry.area.sum())
    area_sqkm = area_sqm / 1_000_000
    logger.info(f"  boundary area: {area_sqkm:.1f} km² ({area_sqm:,.0f} m²)")

    # Sanity check: Chicago is ~589 km² per DATA_SOURCES.md
    if not (500 < area_sqkm < 700):
        raise ValueError(f"Chicago boundary area {area_sqkm:.1f} km² is implausible (expected ~589)")

    boundary.to_file(out, driver="GPKG")
    logger.info(f"wrote {out}")
    return boundary


def process_tracts(boundary):
    """Join population onto Cook County tracts, reproject, clip to Chicago."""
    import geopandas as gpd
    import pandas as pd

    out = config.TRACTS_S2
    if should_skip(out, force=False):
        return gpd.read_file(out)

    logger.info(f"load  {config.TRACTS_RAW}")
    tracts = gpd.read_file(config.TRACTS_RAW)
    logger.info(f"  raw tracts: {len(tracts)} features, CRS={tracts.crs}, cols={tracts.columns.tolist()}")

    logger.info(f"load  {config.POPULATION_RAW}")
    pop = pd.read_csv(config.POPULATION_RAW, dtype={"GEO_ID": str, "GEOID": str})
    logger.info(f"  raw population: {len(pop)} rows, cols={pop.columns.tolist()}")

    # Ensure GEOID is string on both sides for a clean join
    tracts["GEOID"] = tracts["GEOID"].astype(str)

    matched = tracts["GEOID"].isin(pop["GEOID"]).sum()
    logger.info(f"  GEOID overlap: {matched}/{len(tracts)} tracts have population data")

    tracts = tracts.merge(pop[["GEOID", "population"]], on="GEOID", how="left")
    tracts["population"] = tracts["population"].fillna(0).astype(int)
    logger.info(f"  after join: pop total={int(tracts['population'].sum()):,}, "
                f"min={int(tracts['population'].min())}, max={int(tracts['population'].max())}")

    tracts = tracts.to_crs(config.PROJECT_CRS)
    tracts = _clean_geometry(tracts)
    _assert_project_crs(tracts, "tracts")

    before_clip = len(tracts)
    tracts = gpd.clip(tracts, boundary)
    tracts = _clean_geometry(tracts, geom_types={"Polygon", "MultiPolygon"})
    logger.info(f"  clip to Chicago: {before_clip} → {len(tracts)} tracts (polygons only)")

    tracts["area_sqm"] = tracts.geometry.area
    logger.info(f"  area_sqm: min={tracts['area_sqm'].min():,.0f}, "
                f"median={tracts['area_sqm'].median():,.0f}, "
                f"max={tracts['area_sqm'].max():,.0f}")

    total_pop_chicago = int(tracts["population"].sum())
    logger.info(f"  Chicago total population (post-clip): {total_pop_chicago:,}")

    tracts.to_file(out, driver="GPKG")
    logger.info(f"wrote {out}")
    return tracts


def process_clinics(boundary):
    """Load raw clinics (EPSG:4326), reproject, clip to Chicago boundary."""
    import geopandas as gpd

    out = config.CLINICS_S2
    if should_skip(out, force=False):
        return gpd.read_file(out)

    logger.info(f"load  {config.CLINICS_RAW}")
    clinics = gpd.read_file(config.CLINICS_RAW)
    logger.info(f"  raw clinics: {len(clinics)} features, CRS={clinics.crs}, cols={clinics.columns.tolist()}")

    clinics = clinics.to_crs(config.PROJECT_CRS)
    clinics = _clean_geometry(clinics, geom_types={"Point", "MultiPoint"})
    _assert_project_crs(clinics, "clinics")

    before_clip = len(clinics)
    clinics = gpd.clip(clinics, boundary)
    clinics = _clean_geometry(clinics, geom_types={"Point", "MultiPoint"})
    logger.info(f"  clip to Chicago: {before_clip} → {len(clinics)} clinics (inside boundary)")

    # Keep only the columns we actually use downstream
    keep = [c for c in ["name", "facility_type", "source", "geometry"] if c in clinics.columns]
    clinics = clinics[keep].reset_index(drop=True)

    logger.info(f"  final columns: {clinics.columns.tolist()}")
    if "source" in clinics.columns:
        logger.info(f"  source breakdown:\n{clinics['source'].value_counts()}")

    clinics.to_file(out, driver="GPKG")
    logger.info(f"wrote {out}")
    return clinics


def run(force: bool = False) -> None:
    logger.info("=== Stage 2: Reproject ===")
    boundary = process_boundary()
    tracts = process_tracts(boundary)
    clinics = process_clinics(boundary)
    logger.info(f"Stage 2 complete — {len(tracts)} tracts, {len(clinics)} clinics")

"""Stage 1: Ingest.

Downloads all raw data to data/raw/. No spatial operations, no reprojection.
Skips any file that already exists unless force=True.
"""

import logging
import os

import config
from pipeline._common import load_env, should_skip

logger = logging.getLogger(__name__)


def download_census_tracts(force: bool = False) -> None:
    out = config.TRACTS_RAW
    if should_skip(out, force):
        return

    import pygris

    logger.info(f"pygris.tracts(state={config.STATE_FIPS}, county={config.COUNTY_FIPS}, year=2020)")
    tracts = pygris.tracts(
        state=config.STATE_FIPS,
        county=config.COUNTY_FIPS,
        year=2020,
    )

    keep = ["GEOID", "NAME", "ALAND", "AWATER", "geometry"]
    keep = [c for c in keep if c in tracts.columns]
    tracts = tracts[keep]

    logger.info(f"tracts downloaded: rows={len(tracts):,}, cols={tracts.columns.tolist()}")
    logger.info(f"tracts CRS: {tracts.crs}")
    logger.info(f"first GEOID sample: {tracts['GEOID'].head(3).tolist()}")

    tracts.to_file(out, driver="GeoJSON")
    logger.info(f"wrote  {out}")


def download_population(force: bool = False) -> None:
    out = config.POPULATION_RAW
    if should_skip(out, force):
        return

    import pandas as pd
    import requests

    url = f"{config.CENSUS_API_BASE}/{config.CENSUS_ACS_YEAR}/acs/acs5"
    params = {
        "get": f"{config.CENSUS_POP_TABLE},GEO_ID",
        "for": "tract:*",
        "in": f"state:{config.STATE_FIPS} county:{config.COUNTY_FIPS}",
    }
    api_key = os.getenv("CENSUS_API_KEY", "")
    if api_key:
        params["key"] = api_key

    logger.info(f"GET {url}  params(get={params['get']}, in={params['in']})")
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    headers, *rows = data
    df = pd.DataFrame(rows, columns=headers)
    logger.info(f"ACS response: rows={len(df):,}, cols={df.columns.tolist()}")
    logger.info(f"first record: {df.iloc[0].to_dict()}")

    df = df.rename(columns={config.CENSUS_POP_TABLE: "population"})
    df["population"] = pd.to_numeric(df["population"], errors="coerce").fillna(0).astype(int)
    df.loc[df["population"] < 0, "population"] = 0

    df["GEOID"] = df["GEO_ID"].str[-11:]

    total = int(df["population"].sum())
    logger.info(f"population rows={len(df):,}, total={total:,}, "
                f"min={int(df['population'].min())}, max={int(df['population'].max())}")

    df.to_csv(out, index=False)
    logger.info(f"wrote  {out}")


def _fetch_portal(dataset_id: str) -> "pd.DataFrame":
    """Hit a Chicago Data Portal dataset. Logs columns + first record
    (Live API Inspection Rule) before returning."""
    import pandas as pd
    import requests

    url = f"{config.CHICAGO_PORTAL_BASE}/{dataset_id}.json"
    params = {"$limit": config.CLINICS_PAGE_LIMIT}

    logger.info(f"GET {url}  params={params}")
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    records = resp.json()
    if not isinstance(records, list):
        raise ValueError(f"Expected JSON array from {url}, got {type(records).__name__}")

    df = pd.DataFrame(records)
    logger.info(f"  → {dataset_id}: {len(df)} rows, cols={df.columns.tolist()}")
    if len(df):
        logger.info(f"  → first record: {df.iloc[0].to_dict()}")
    return df


def _extract_cdph_clinics(df):
    """Dataset kcki-hnch: top-level 'latitude'/'longitude', 'site_name', 'clinic_type'."""
    import pandas as pd

    if not {"latitude", "longitude", "site_name"}.issubset(df.columns):
        raise ValueError(f"kcki-hnch schema changed — got cols: {df.columns.tolist()}")

    out = pd.DataFrame({
        "name": df["site_name"],
        "facility_type": df.get("clinic_type", ""),
        "source": "cdph_clinics",
        "longitude": pd.to_numeric(df["longitude"], errors="coerce"),
        "latitude": pd.to_numeric(df["latitude"], errors="coerce"),
    })
    return out


def _extract_community_centers(df):
    """Dataset cjg8-dbka: coords nested in location_1 = {latitude, longitude, human_address}.
    Name lives in 'facility'."""
    import pandas as pd

    if "facility" not in df.columns or "location_1" not in df.columns:
        raise ValueError(f"cjg8-dbka schema changed — got cols: {df.columns.tolist()}")

    def get_coord(loc, key):
        if isinstance(loc, dict):
            return loc.get(key)
        return None

    out = pd.DataFrame({
        "name": df["facility"],
        "facility_type": "Community Health Center",
        "source": "community_centers",
        "longitude": pd.to_numeric(df["location_1"].apply(lambda v: get_coord(v, "longitude")), errors="coerce"),
        "latitude":  pd.to_numeric(df["location_1"].apply(lambda v: get_coord(v, "latitude")),  errors="coerce"),
    })
    return out


def download_clinics(force: bool = False) -> None:
    out = config.CLINICS_RAW
    if should_skip(out, force):
        return

    import geopandas as gpd
    import pandas as pd

    cdph_raw = _fetch_portal(config.CLINICS_CDPH_ID)
    cdph = _extract_cdph_clinics(cdph_raw)
    logger.info(f"cdph extracted: {len(cdph)} rows")

    cc_raw = _fetch_portal(config.CLINICS_COMMUNITY_CENTERS_ID)
    cc = _extract_community_centers(cc_raw)
    logger.info(f"community centers extracted: {len(cc)} rows")

    combined = pd.concat([cdph, cc], ignore_index=True)
    before = len(combined)
    combined = combined.dropna(subset=["longitude", "latitude"])
    combined = combined[(combined["longitude"] != 0) & (combined["latitude"] != 0)]
    logger.info(f"after null/zero coord filter: {before} → {len(combined)} rows")

    # De-duplicate facilities at identical coordinates (CDPH and community center
    # datasets can overlap at the same site).
    before_dedup = len(combined)
    combined["_lon_key"] = combined["longitude"].round(5)
    combined["_lat_key"] = combined["latitude"].round(5)
    combined = combined.drop_duplicates(subset=["_lon_key", "_lat_key"]).drop(columns=["_lon_key", "_lat_key"])
    logger.info(f"after coord-dedup: {before_dedup} → {len(combined)} rows")

    if len(combined) == 0:
        raise ValueError("Zero clinic records after cleanup — check API responses")

    gdf = gpd.GeoDataFrame(
        combined.reset_index(drop=True),
        geometry=gpd.points_from_xy(combined["longitude"], combined["latitude"]),
        crs="EPSG:4326",
    )

    logger.info(f"clinics final: {len(gdf)} features, CRS={gdf.crs}")
    logger.info(f"source breakdown:\n{gdf['source'].value_counts()}")
    logger.info(f"facility_type top 8:\n{gdf['facility_type'].value_counts().head(8)}")

    gdf.to_file(out, driver="GeoJSON")
    logger.info(f"wrote  {out}")


def download_road_network(force: bool = False) -> None:
    out = config.GRAPH_RAW
    if should_skip(out, force):
        return

    import osmnx as ox

    logger.info(f"ox.graph_from_place({config.CHICAGO_PLACE!r}, network_type={config.NETWORK_TYPE!r})")
    logger.info("this takes 2-5 minutes — Overpass API query for the entire Chicago road graph")
    G = ox.graph_from_place(config.CHICAGO_PLACE, network_type=config.NETWORK_TYPE)
    logger.info(f"graph downloaded: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

    logger.info(f"add_edge_speeds(hwy_speeds=ROAD_SPEEDS, fallback={config.DEFAULT_SPEED})")
    G = ox.add_edge_speeds(G, hwy_speeds=config.ROAD_SPEEDS, fallback=float(config.DEFAULT_SPEED))

    logger.info("add_edge_travel_times")
    G = ox.add_edge_travel_times(G)

    # Sanity check: travel_time is on edges
    sample_edge = next(iter(G.edges(data=True)))
    edge_attrs = sample_edge[2]
    if "travel_time" not in edge_attrs:
        raise ValueError(f"travel_time missing after add_edge_travel_times — edge attrs: {list(edge_attrs.keys())}")
    logger.info(f"sample edge attrs: keys={list(edge_attrs.keys())}, "
                f"speed_kph={edge_attrs.get('speed_kph')}, travel_time={edge_attrs.get('travel_time')}")

    ox.save_graphml(G, out)
    import os as _os
    size_mb = _os.path.getsize(out) / (1024 * 1024)
    logger.info(f"wrote  {out}  ({size_mb:.1f} MB)")


def download_city_boundary(force: bool = False) -> None:
    out = config.BOUNDARY_RAW
    if should_skip(out, force):
        return

    import pygris

    logger.info(f"pygris.places(state={config.STATE_FIPS})")
    places = pygris.places(state=config.STATE_FIPS)
    chicago = places[places["NAME"] == "Chicago"].copy()
    logger.info(f"places query: {len(places)} total, {len(chicago)} match NAME='Chicago'")

    if len(chicago) == 0:
        raise ValueError("Chicago not found in pygris places output")
    if len(chicago) > 1:
        logger.warning(f"expected 1 Chicago polygon, got {len(chicago)} — keeping all")

    logger.info(f"boundary CRS: {chicago.crs}, geom types: {chicago.geometry.geom_type.unique().tolist()}")
    chicago.to_file(out, driver="GeoJSON")
    logger.info(f"wrote  {out}")


def run(force: bool = False) -> None:
    load_env()
    logger.info("=== Stage 1: Ingest ===")
    download_census_tracts(force=force)
    download_population(force=force)
    download_clinics(force=force)
    download_road_network(force=force)
    download_city_boundary(force=force)
    logger.info("Stage 1 complete")

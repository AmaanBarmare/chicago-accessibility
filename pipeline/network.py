"""Stage 3: Network.

Loads the OSMnx road graph and generates drive-time isochrones from every
existing clinic at 10-minute and 20-minute thresholds. Dissolves per-clinic
isochrones into city-wide service-area unions.
"""

import logging

import config
from pipeline._common import should_skip

logger = logging.getLogger(__name__)


def load_graph():
    import osmnx as ox
    logger.info(f"load graph  {config.GRAPH_RAW}")
    G = ox.load_graphml(config.GRAPH_RAW)
    logger.info(f"  graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

    sample = next(iter(G.edges(data=True)))
    if "travel_time" not in sample[2]:
        raise ValueError("graph missing travel_time on edges — rerun Stage 1 to regenerate")
    return G


def _isochrone_polygon(G, node_id, travel_time_seconds):
    """Return a Shapely polygon in EPSG:26916 (metres) for the drive-time
    isochrone from `node_id`, or None if too few reachable nodes to form a
    polygon."""
    import geopandas as gpd
    import networkx as nx
    from shapely.geometry import MultiPoint

    subgraph = nx.ego_graph(
        G, node_id, radius=travel_time_seconds, distance="travel_time"
    )
    pts = [(d["x"], d["y"]) for _, d in subgraph.nodes(data=True)]
    if len(pts) < 3:
        return None

    hull_4326 = MultiPoint(pts).convex_hull
    # The convex hull of 3+ Points is a Polygon; but if the points are
    # collinear we can still get a LineString. Reject those.
    if hull_4326.geom_type not in ("Polygon", "MultiPolygon"):
        return None

    gs = gpd.GeoSeries([hull_4326], crs="EPSG:4326").to_crs(config.PROJECT_CRS)
    return gs.iloc[0]


def _compute_all_isochrones(G, clinics_gdf, travel_times):
    """For each clinic × travel_time, compute a polygon. Returns a dict
    mapping travel_time -> GeoDataFrame of per-clinic polygons."""
    import geopandas as gpd
    import osmnx as ox
    from pyproj import Transformer

    # Clinics are in EPSG:26916 (metres); OSMnx needs lon/lat.
    transformer = Transformer.from_crs(config.PROJECT_CRS, "EPSG:4326", always_xy=True)
    lons, lats = transformer.transform(
        clinics_gdf.geometry.x.values, clinics_gdf.geometry.y.values
    )

    # Batch nearest-node lookup — much faster than looping.
    logger.info(f"batch nearest-node lookup for {len(clinics_gdf)} clinics")
    nearest_nodes = ox.nearest_nodes(G, X=list(lons), Y=list(lats))
    logger.info(f"  nearest nodes: min={min(nearest_nodes)}, max={max(nearest_nodes)}, "
                f"unique={len(set(nearest_nodes))}")

    results = {tt: [] for tt in travel_times}
    fail_counts = {tt: 0 for tt in travel_times}
    n = len(clinics_gdf)

    for idx, (_, clinic) in enumerate(clinics_gdf.iterrows(), start=1):
        node_id = int(nearest_nodes[idx - 1])
        name = str(clinic.get("name", f"clinic_{idx}"))

        for tt in travel_times:
            try:
                poly = _isochrone_polygon(G, node_id, tt)
            except Exception as e:
                logger.warning(f"  clinic {idx}/{n} '{name[:40]}' tt={tt}s: {e}")
                poly = None

            if poly is None:
                fail_counts[tt] += 1
            else:
                results[tt].append({
                    "clinic_idx": idx - 1,
                    "name": name,
                    "facility_type": clinic.get("facility_type", ""),
                    "travel_time_s": tt,
                    "geometry": poly,
                })

        if idx % 10 == 0 or idx == n:
            logger.info(
                f"  progress {idx}/{n}  "
                f"ok_10={len(results[config.TRAVEL_TIME_10MIN])}  "
                f"ok_20={len(results[config.TRAVEL_TIME_20MIN])}"
            )

    for tt in travel_times:
        logger.info(f"travel_time={tt}s: {len(results[tt])} isochrones, {fail_counts[tt]} failures")

    out = {}
    for tt in travel_times:
        out[tt] = gpd.GeoDataFrame(results[tt], crs=config.PROJECT_CRS)
    return out


def _dissolve(iso_gdf):
    """Collapse a per-clinic GeoDataFrame into a single union polygon."""
    import geopandas as gpd
    if len(iso_gdf) == 0:
        return gpd.GeoDataFrame({"geometry": []}, crs=config.PROJECT_CRS)
    dissolved = iso_gdf.copy()
    dissolved["_dissolve_key"] = 1
    dissolved = dissolved.dissolve(by="_dissolve_key").reset_index(drop=True)
    return dissolved[["geometry"]]


def run(force: bool = False) -> None:
    logger.info("=== Stage 3: Network ===")

    import os
    outputs = [config.ISO_10MIN_S3, config.ISO_20MIN_S3,
               config.ISO_10MIN_IND_S3, config.ISO_20MIN_IND_S3]
    if not force and all(os.path.exists(p) and os.path.getsize(p) > 0 for p in outputs):
        for p in outputs:
            logger.info(f"skip (exists)  {p}")
        return

    import geopandas as gpd

    logger.info(f"load clinics  {config.CLINICS_S2}")
    clinics = gpd.read_file(config.CLINICS_S2)
    if clinics.crs is None or clinics.crs.to_epsg() != 26916:
        raise ValueError(f"clinics CRS {clinics.crs} != EPSG:26916 — rerun Stage 2")
    logger.info(f"  clinics: {len(clinics)} features")

    G = load_graph()

    travel_times = [config.TRAVEL_TIME_10MIN, config.TRAVEL_TIME_20MIN]
    per_clinic = _compute_all_isochrones(G, clinics, travel_times)

    # Save per-clinic layers
    per_clinic[config.TRAVEL_TIME_10MIN].to_file(config.ISO_10MIN_IND_S3, driver="GPKG")
    logger.info(f"wrote {config.ISO_10MIN_IND_S3}  ({len(per_clinic[config.TRAVEL_TIME_10MIN])} features)")
    per_clinic[config.TRAVEL_TIME_20MIN].to_file(config.ISO_20MIN_IND_S3, driver="GPKG")
    logger.info(f"wrote {config.ISO_20MIN_IND_S3}  ({len(per_clinic[config.TRAVEL_TIME_20MIN])} features)")

    # Dissolve to city-wide unions
    iso_10 = _dissolve(per_clinic[config.TRAVEL_TIME_10MIN])
    iso_20 = _dissolve(per_clinic[config.TRAVEL_TIME_20MIN])

    area_10 = float(iso_10.geometry.area.sum()) / 1_000_000
    area_20 = float(iso_20.geometry.area.sum()) / 1_000_000
    chicago_area_km2 = 607.0  # from Stage 2
    logger.info(
        f"dissolved coverage:  10-min={area_10:.1f} km² ({100*area_10/chicago_area_km2:.1f}% of Chicago), "
        f"20-min={area_20:.1f} km² ({100*area_20/chicago_area_km2:.1f}% of Chicago)"
    )

    iso_10.to_file(config.ISO_10MIN_S3, driver="GPKG")
    logger.info(f"wrote {config.ISO_10MIN_S3}")
    iso_20.to_file(config.ISO_20MIN_S3, driver="GPKG")
    logger.info(f"wrote {config.ISO_20MIN_S3}")

    logger.info("Stage 3 complete")

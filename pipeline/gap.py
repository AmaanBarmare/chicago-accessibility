"""Stage 4: Gap.

Computes per-tract coverage fraction from the dissolved isochrones, the
population-weighted gap score, and identifies the top-N recommended new
clinic locations as centroids of the highest-scoring tracts.
"""

import logging

import config
from pipeline._common import should_skip

logger = logging.getLogger(__name__)


def _assert_crs(gdf, label: str) -> None:
    epsg = gdf.crs.to_epsg() if gdf.crs is not None else None
    if epsg != 26916:
        raise ValueError(f"{label}: expected EPSG:26916, got {gdf.crs}")


def compute_coverage_fraction(tracts, iso_gdf, col_name):
    """Add `col_name` to tracts giving the fraction of each tract's area
    inside the dissolved isochrone union."""
    _assert_crs(tracts, "tracts")
    _assert_crs(iso_gdf, f"iso_gdf[{col_name}]")

    iso_union = iso_gdf.geometry.union_all()

    def frac(geom):
        if geom is None or geom.is_empty or geom.area <= 0:
            return 0.0
        inter = geom.intersection(iso_union).area
        return max(0.0, min(1.0, inter / geom.area))

    tracts = tracts.copy()
    tracts[col_name] = tracts.geometry.apply(frac)
    return tracts


def compute_gap_scores(tracts):
    tracts = tracts.copy()
    tracts["gap_score"] = (tracts["population"] * (1.0 - tracts["coverage_10min"])).round(2)
    tracts["gap_score_20min"] = (tracts["population"] * (1.0 - tracts["coverage_20min"])).round(2)
    # Guard: negatives are impossible by construction but defensively clip
    tracts["gap_score"] = tracts["gap_score"].clip(lower=0)
    tracts["gap_score_20min"] = tracts["gap_score_20min"].clip(lower=0)
    return tracts


def identify_top_gaps(tracts, n):
    """Return a GeoDataFrame of n points (centroids of the top-n gap tracts)
    with rank + human-readable recommendation column."""
    import geopandas as gpd

    top = tracts.nlargest(n, "gap_score").copy().reset_index(drop=True)
    top["geometry"] = top.geometry.centroid
    top["rank"] = range(1, len(top) + 1)

    # Also add lat/lon in WGS84 for the PDF brief
    top_wgs = top.to_crs("EPSG:4326")
    top["lon_wgs84"] = top_wgs.geometry.x.round(5)
    top["lat_wgs84"] = top_wgs.geometry.y.round(5)

    top["recommendation"] = top.apply(
        lambda r: (
            f"Rank {int(r['rank'])}: tract {r['NAME']} — "
            f"population {int(r['population']):,}, "
            f"10-min coverage {r['coverage_10min']:.1%}, "
            f"gap score {r['gap_score']:,.0f}"
        ),
        axis=1,
    )
    keep = ["rank", "GEOID", "NAME", "population", "coverage_10min", "coverage_20min",
            "gap_score", "gap_score_20min", "lat_wgs84", "lon_wgs84", "recommendation", "geometry"]
    return gpd.GeoDataFrame(top[keep], crs=config.PROJECT_CRS)


def log_summary(tracts):
    total_pop = int(tracts["population"].sum())
    # "Covered" = any positive coverage. More useful framing: population-weighted mean coverage.
    weighted_cov_10 = (tracts["population"] * tracts["coverage_10min"]).sum() / max(total_pop, 1)
    weighted_cov_20 = (tracts["population"] * tracts["coverage_20min"]).sum() / max(total_pop, 1)

    pop_fully_uncov_10 = int(tracts.loc[tracts["coverage_10min"] == 0, "population"].sum())
    pop_any_cov_10 = total_pop - pop_fully_uncov_10
    pop_fully_uncov_20 = int(tracts.loc[tracts["coverage_20min"] == 0, "population"].sum())

    logger.info("=== Gap Summary ===")
    logger.info(f"  total Chicago population (Stage 2 clipped): {total_pop:,}")
    logger.info(f"  population-weighted mean coverage @ 10 min: {weighted_cov_10:.1%}")
    logger.info(f"  population-weighted mean coverage @ 20 min: {weighted_cov_20:.1%}")
    logger.info(f"  population with ANY 10-min coverage        : {pop_any_cov_10:,} ({100*pop_any_cov_10/total_pop:.1f}%)")
    logger.info(f"  population with NO 10-min coverage         : {pop_fully_uncov_10:,} ({100*pop_fully_uncov_10/total_pop:.1f}%)")
    logger.info(f"  population with NO 20-min coverage         : {pop_fully_uncov_20:,} ({100*pop_fully_uncov_20/total_pop:.1f}%)")

    top10 = tracts.nlargest(10, "gap_score")[
        ["GEOID", "NAME", "population", "coverage_10min", "gap_score"]
    ]
    logger.info("  top 10 most underserved tracts:")
    for _, r in top10.iterrows():
        logger.info(
            f"    {r['GEOID']}  tract {r['NAME']:>8}  "
            f"pop={int(r['population']):>6,}  cov10={r['coverage_10min']:.1%}  "
            f"gap={r['gap_score']:>9,.0f}"
        )
    return {
        "total_population": total_pop,
        "pop_any_cov_10": pop_any_cov_10,
        "pop_no_cov_10": pop_fully_uncov_10,
        "pop_no_cov_20": pop_fully_uncov_20,
        "weighted_cov_10": round(weighted_cov_10, 4),
        "weighted_cov_20": round(weighted_cov_20, 4),
    }


def run(force: bool = False) -> None:
    import geopandas as gpd

    logger.info("=== Stage 4: Gap ===")

    if (not force
            and should_skip(config.TRACTS_S4, force=False)
            and should_skip(config.GAP_POINTS_S4, force=False)):
        return

    logger.info(f"load  {config.TRACTS_S2}")
    tracts = gpd.read_file(config.TRACTS_S2)
    _assert_crs(tracts, "tracts")
    logger.info(f"  {len(tracts)} tracts loaded")

    iso_10 = gpd.read_file(config.ISO_10MIN_S3)
    iso_20 = gpd.read_file(config.ISO_20MIN_S3)

    logger.info("compute coverage_10min")
    tracts = compute_coverage_fraction(tracts, iso_10, "coverage_10min")
    logger.info(f"  coverage_10min: min={tracts['coverage_10min'].min():.3f}, "
                f"median={tracts['coverage_10min'].median():.3f}, "
                f"mean={tracts['coverage_10min'].mean():.3f}, "
                f"max={tracts['coverage_10min'].max():.3f}")

    logger.info("compute coverage_20min")
    tracts = compute_coverage_fraction(tracts, iso_20, "coverage_20min")
    logger.info(f"  coverage_20min: min={tracts['coverage_20min'].min():.3f}, "
                f"median={tracts['coverage_20min'].median():.3f}, "
                f"mean={tracts['coverage_20min'].mean():.3f}, "
                f"max={tracts['coverage_20min'].max():.3f}")

    tracts = compute_gap_scores(tracts)
    logger.info(f"  gap_score: min={tracts['gap_score'].min():.0f}, "
                f"median={tracts['gap_score'].median():.0f}, "
                f"max={tracts['gap_score'].max():.0f}")

    log_summary(tracts)

    top = identify_top_gaps(tracts, config.TOP_N_RECOMMENDATIONS)
    logger.info(f"top {len(top)} recommended locations:")
    for _, r in top.iterrows():
        logger.info(f"  {r['recommendation']}")
        logger.info(f"    centroid WGS84: ({r['lat_wgs84']:.5f}, {r['lon_wgs84']:.5f})")

    tracts.to_file(config.TRACTS_S4, driver="GPKG")
    logger.info(f"wrote {config.TRACTS_S4}")
    top.to_file(config.GAP_POINTS_S4, driver="GPKG")
    logger.info(f"wrote {config.GAP_POINTS_S4}")

    logger.info("Stage 4 complete")

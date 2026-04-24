"""Stage 5: Export.

Assembles all final layers into a single GeoPackage and programmatically
generates a one-page PDF recommendation brief with ReportLab.
"""

import logging
import os
from datetime import datetime

import config

logger = logging.getLogger(__name__)


def build_geopackage():
    import geopandas as gpd

    out = config.FINAL_GPKG
    if os.path.exists(out) and os.path.getsize(out) > 0:
        logger.info(f"skip (exists)  {out}")
        return

    sources = [
        (config.TRACTS_S4,      config.GPKG_TRACTS),
        (config.ISO_10MIN_S3,   config.GPKG_ISO_10),
        (config.ISO_20MIN_S3,   config.GPKG_ISO_20),
        (config.CLINICS_S2,     config.GPKG_CLINICS),
        (config.GAP_POINTS_S4,  config.GPKG_GAP_POINTS),
    ]

    for i, (src, layer_name) in enumerate(sources):
        gdf = gpd.read_file(src)
        mode = "w" if i == 0 else "a"
        gdf.to_file(out, layer=layer_name, driver="GPKG", mode=mode)
        logger.info(f"  wrote layer '{layer_name}'  ({len(gdf)} features)  mode={mode}")

    # Verify all layers readable
    import fiona
    layers = fiona.listlayers(out)
    logger.info(f"final GeoPackage layers: {layers}")
    size_kb = os.path.getsize(out) / 1024
    logger.info(f"wrote {out}  ({size_kb:.0f} KB)")


def _coverage_stats(tracts):
    total_pop = int(tracts["population"].sum())
    weighted_cov_10 = (tracts["population"] * tracts["coverage_10min"]).sum() / max(total_pop, 1)
    weighted_cov_20 = (tracts["population"] * tracts["coverage_20min"]).sum() / max(total_pop, 1)
    pop_no_cov_10 = int(tracts.loc[tracts["coverage_10min"] == 0, "population"].sum())
    pop_no_cov_20 = int(tracts.loc[tracts["coverage_20min"] == 0, "population"].sum())
    return {
        "total_pop": total_pop,
        "weighted_cov_10": weighted_cov_10,
        "weighted_cov_20": weighted_cov_20,
        "pop_no_cov_10": pop_no_cov_10,
        "pop_no_cov_20": pop_no_cov_20,
    }


def build_pdf_brief():
    import geopandas as gpd
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    out = config.BRIEF_PDF
    if os.path.exists(out) and os.path.getsize(out) > 0:
        logger.info(f"skip (exists)  {out}")
        return

    tracts = gpd.read_file(config.TRACTS_S4)
    gap_points = gpd.read_file(config.GAP_POINTS_S4)
    clinics = gpd.read_file(config.CLINICS_S2)
    stats = _coverage_stats(tracts)

    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, leading=10)
    footnote = ParagraphStyle("foot", parent=small, textColor=colors.grey)

    doc = SimpleDocTemplate(
        out, pagesize=letter,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.4 * inch, bottomMargin=0.4 * inch,
    )
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, spaceBefore=2, spaceAfter=3)
    h4 = ParagraphStyle("h4", parent=styles["Heading4"], fontSize=10, spaceBefore=2, spaceAfter=2)
    title = ParagraphStyle("titleX", parent=styles["Title"], fontSize=15, spaceAfter=2)
    subtitle = ParagraphStyle("sub", parent=styles["Heading4"], fontSize=10, textColor=colors.grey, spaceAfter=4)
    story = []

    story.append(Paragraph("Chicago Healthcare Accessibility — Clinic Siting Recommendations",
                           title))
    story.append(Paragraph("Drive-time gap analysis of CDPH and community health clinics",
                           subtitle))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.black))
    story.append(Spacer(1, 0.05 * inch))

    # Coverage summary table
    story.append(Paragraph("Coverage Summary", h2))
    summary_rows = [
        ["Metric", "Value"],
        ["Total Chicago population (analysed)", f"{stats['total_pop']:,}"],
        ["Existing clinics analysed", f"{len(clinics):,}"],
        ["Population-weighted coverage @ 10 min", f"{stats['weighted_cov_10']:.1%}"],
        ["Population-weighted coverage @ 20 min", f"{stats['weighted_cov_20']:.1%}"],
        ["Population with no 10-min coverage", f"{stats['pop_no_cov_10']:,}"],
        ["Population with no 20-min coverage", f"{stats['pop_no_cov_20']:,}"],
    ]
    summary_tbl = Table(summary_rows, colWidths=[3.6 * inch, 2.8 * inch])
    summary_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E5C8A")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("GRID",       (0, 0), (-1, -1), 0.3, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ]))
    story.append(summary_tbl)
    story.append(Spacer(1, 0.08 * inch))

    # Top 10 underserved tracts
    story.append(Paragraph("Top 10 Most Underserved Census Tracts", h2))
    top10 = tracts.nlargest(10, "gap_score")
    t10_rows = [["Rank", "GEOID", "Tract", "Population", "10-min cov.", "Gap score"]]
    for i, (_, r) in enumerate(top10.iterrows(), start=1):
        t10_rows.append([
            str(i),
            str(r["GEOID"]),
            str(r["NAME"]),
            f"{int(r['population']):,}",
            f"{r['coverage_10min']:.1%}",
            f"{r['gap_score']:,.0f}",
        ])
    t10_tbl = Table(t10_rows, colWidths=[0.45*inch, 1.1*inch, 0.8*inch, 1.0*inch, 0.9*inch, 0.9*inch])
    t10_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E5C8A")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ("GRID",       (0, 0), (-1, -1), 0.3, colors.grey),
        ("ALIGN",      (3, 1), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ]))
    story.append(t10_tbl)
    story.append(Spacer(1, 0.08 * inch))

    # Top 3 recommendations — tabular form to save space
    story.append(Paragraph("Top 3 Recommended New Clinic Locations", h2))
    rec_rows = [["Rank", "Tract (GEOID)", "Coordinates (WGS84)", "Pop.",
                 "10-min cov.", "Gap score"]]
    for _, r in gap_points.iterrows():
        rec_rows.append([
            str(int(r["rank"])),
            f"{r['NAME']} ({r['GEOID']})",
            f"{r['lat_wgs84']:.5f}°N, {abs(r['lon_wgs84']):.5f}°W",
            f"{int(r['population']):,}",
            f"{r['coverage_10min']:.1%}",
            f"{r['gap_score']:,.0f}",
        ])
    rec_tbl = Table(rec_rows, colWidths=[0.45*inch, 1.5*inch, 1.85*inch, 0.7*inch, 0.85*inch, 0.85*inch])
    rec_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E5C8A")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ("GRID",       (0, 0), (-1, -1), 0.3, colors.grey),
        ("ALIGN",      (3, 1), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ]))
    story.append(rec_tbl)
    story.append(Spacer(1, 0.08 * inch))

    # Footer / methodology
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 0.05 * inch))
    methodology = (
        "<b>Methodology.</b> Drive-time isochrones were computed on the Chicago "
        "OpenStreetMap road network using OSMnx and NetworkX (Dijkstra's algorithm), "
        "with per-road-type speed assumptions to convert edge lengths to travel "
        "times. For each census tract, coverage fraction is the share of the tract's "
        "area that falls inside the union of 10-minute isochrones from all existing "
        "clinics. Gap score = population &times; (1 &minus; coverage_10min). The "
        "top-3 recommended locations are the centroids of the three highest-scoring "
        "tracts."
    )
    story.append(Paragraph(methodology, small))
    story.append(Spacer(1, 0.04 * inch))
    caveat = (
        "<b>Scope caveat.</b> The clinic dataset here is the City of Chicago "
        "Department of Public Health clinics plus federally-funded community "
        "health centers. Commercial urgent-care chains (e.g. hospital-affiliated "
        "walk-in clinics) are not published cleanly in the Chicago Data Portal "
        "and are not included. Recommendations therefore identify gaps in "
        "<i>public and community health clinic</i> coverage specifically."
    )
    story.append(Paragraph(caveat, small))
    story.append(Spacer(1, 0.04 * inch))
    sources = (
        "<b>Data sources.</b> US Census Bureau TIGER and ACS 2022 (tracts + "
        "population); City of Chicago Data Portal — CDPH Clinic Locations "
        "(kcki-hnch) and Primary Care Community Health Centers (cjg8-dbka); "
        "OpenStreetMap contributors via OSMnx (ODbL). "
        f"Analysis date: {datetime.now().strftime('%B %Y')}."
    )
    story.append(Paragraph(sources, footnote))

    doc.build(story)
    size_kb = os.path.getsize(out) / 1024
    logger.info(f"wrote {out}  ({size_kb:.0f} KB)")


def run(force: bool = False) -> None:
    logger.info("=== Stage 5: Export ===")
    build_geopackage()
    build_pdf_brief()
    logger.info("Stage 5 complete")

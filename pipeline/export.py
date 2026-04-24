"""Stage 5: Export.

Assembles all final layers into a single GeoPackage and programmatically
generates a one-page PDF recommendation brief with ReportLab.
"""

import logging

logger = logging.getLogger(__name__)


def run(force: bool = False) -> None:
    raise NotImplementedError("Stage 5 (export) not yet implemented")

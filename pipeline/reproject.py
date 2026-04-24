"""Stage 2: Reproject.

Reprojects raw data to EPSG:26916, validates geometries, and clips to the
Chicago city boundary. Reads from data/raw/ and writes to data/processed/stage2/.
"""

import logging

logger = logging.getLogger(__name__)


def run(force: bool = False) -> None:
    raise NotImplementedError("Stage 2 (reproject) not yet implemented")

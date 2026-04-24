"""Stage 3: Network.

Loads the OSMnx road graph and generates drive-time isochrones from every
existing clinic at 10-minute and 20-minute thresholds. Dissolves per-clinic
isochrones into city-wide service-area unions.
"""

import logging

logger = logging.getLogger(__name__)


def run(force: bool = False) -> None:
    raise NotImplementedError("Stage 3 (network) not yet implemented")

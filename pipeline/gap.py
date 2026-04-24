"""Stage 4: Gap.

Computes per-tract coverage fraction from the dissolved isochrones, the
population-weighted gap score, and identifies the top-N recommended new
clinic locations as centroids of the highest-scoring tracts.
"""

import logging

logger = logging.getLogger(__name__)


def run(force: bool = False) -> None:
    raise NotImplementedError("Stage 4 (gap) not yet implemented")

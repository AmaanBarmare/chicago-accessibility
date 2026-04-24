"""Shared helpers for pipeline stages."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_ENV_LOADED = False


def load_env() -> None:
    """Load .env once per process. Idempotent."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    load_dotenv()
    _ENV_LOADED = True


def should_skip(path: str, force: bool) -> bool:
    """Return True if the file exists and we are not forcing a re-download."""
    p = Path(path)
    if p.exists() and p.stat().st_size > 0 and not force:
        logger.info(f"skip (exists)  {path}  ({p.stat().st_size:,} bytes)")
        return True
    return False

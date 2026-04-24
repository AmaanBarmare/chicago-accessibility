"""Single entry point for the Chicago Urgent Care Accessibility pipeline.

Usage:
    python run_pipeline.py --setup
    python run_pipeline.py
    python run_pipeline.py --stage ingest
    python run_pipeline.py --from-stage network
    python run_pipeline.py --force
"""

import argparse
import importlib
import logging
import os
import sys

import config

STAGES = ["ingest", "reproject", "network", "gap", "export"]


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )


def setup_directories() -> None:
    logger = logging.getLogger("setup")
    for d in config.ALL_DIRS:
        os.makedirs(d, exist_ok=True)
        logger.info(f"ensured  {d}")
    logger.info("directory setup complete")


def run_stage(stage: str, force: bool) -> None:
    logger = logging.getLogger("runner")
    logger.info(f"=== stage: {stage} ===")
    module = importlib.import_module(f"pipeline.{stage}")
    module.run(force=force)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Create the data/processed/output directory tree and exit.",
    )
    parser.add_argument(
        "--stage",
        choices=STAGES,
        help="Run a single stage and exit.",
    )
    parser.add_argument(
        "--from-stage",
        dest="from_stage",
        choices=STAGES,
        help="Run this stage and every stage after it.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run work even if outputs already exist.",
    )
    return parser.parse_args()


def main() -> int:
    configure_logging()
    args = parse_args()

    if args.setup:
        setup_directories()
        return 0

    if args.stage and args.from_stage:
        logging.error("--stage and --from-stage are mutually exclusive")
        return 2

    if args.stage:
        stages_to_run = [args.stage]
    elif args.from_stage:
        start = STAGES.index(args.from_stage)
        stages_to_run = STAGES[start:]
    else:
        stages_to_run = STAGES

    for stage in stages_to_run:
        run_stage(stage, force=args.force)

    logging.getLogger("runner").info("pipeline complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())

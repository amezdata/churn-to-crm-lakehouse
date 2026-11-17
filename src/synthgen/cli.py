"""CLI entry point: python -m synthgen --output data/synthetic/brainlab --seed 42"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from synthgen.generate import generate_dataset
from synthgen.writers import write_dataset

LOGGER = logging.getLogger("synthgen")
DEFAULT_OUTPUT = Path("data") / "synthetic" / "brainlab"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate synthetic BrainLab operational sources (CSV + JSON logs)."
    )
    parser.add_argument("--seed", type=int, default=42, help="Generator seed.")
    parser.add_argument(
        "--scale",
        choices=("small", "medium"),
        default="small",
        help="Proof-of-concept volume (small by default).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output directory (CSV + JSONL).",
    )
    parser.add_argument(
        "--overlap-tokens-file",
        type=Path,
        default=None,
        help="Optional file of 16-character STEMStar hex tokens used for the identity overlap.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Write clean tables (no Bronze defects). By default the Bronze mess is added.",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(message)s")
    tables = generate_dataset(
        seed=args.seed,
        scale=args.scale,
        apply_mess=not args.clean,
        overlap_tokens_file=args.overlap_tokens_file,
    )
    written = write_dataset(tables, args.output)
    LOGGER.info("Wrote %s files to %s", len(written), args.output)
    for name, rows in tables.items():
        LOGGER.info("%s: %s rows", name, len(rows))
    return 0

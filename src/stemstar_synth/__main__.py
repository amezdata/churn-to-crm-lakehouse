"""python -m stemstar_synth --output data/synthetic/stemstar --seed 42"""

from __future__ import annotations

import argparse
from pathlib import Path

from stemstar_synth.generate import generate


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic STEMStar extracts.")
    parser.add_argument("--output", type=Path, default=Path("data/synthetic/stemstar"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    manifest = generate(args.output, args.seed)
    print(f"{len(manifest['files'])} files, {sum(manifest['files'].values())} rows -> {args.output}")


if __name__ == "__main__":
    main()

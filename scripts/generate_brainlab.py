"""Generate the BrainLab synthetic CSV/JSON sources.

Usage:
    python scripts/generate_brainlab.py
    python scripts/generate_brainlab.py --scale medium --seed 42
    python scripts/generate_brainlab.py --overlap-tokens-file data/raw/stemstar_tokens.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from synthgen.cli import main


if __name__ == "__main__":
    raise SystemExit(main())

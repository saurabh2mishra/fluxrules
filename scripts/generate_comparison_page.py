"""Regenerate docs/comparing-values.md from the comparison matrix.

Run from the repository root: ``uv run python scripts/generate_comparison_page.py``
(or ``make docs-tables``).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.engine.comparison_page import write  # noqa: E402

if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    print(f"Wrote {write()}")

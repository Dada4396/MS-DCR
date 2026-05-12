#!/usr/bin/env python3
"""Compatibility entry point for running MS-DCR from a source checkout."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from ms_dcr import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Extract a small mzML demo file from a larger source data set."""

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ms_dcr import extract_demo_mzml


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a small mzML demo subset")
    parser.add_argument("-i", "--input", required=True, type=Path)
    parser.add_argument("-o", "--output", required=True, type=Path)
    parser.add_argument("-n", "--spectra-count", type=int, default=32)
    args = parser.parse_args()
    print(json.dumps(extract_demo_mzml(args.input, args.output, args.spectra_count), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

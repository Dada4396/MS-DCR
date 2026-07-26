#!/usr/bin/env python3
"""Smoke test for the repeated MS-DCR benchmark runner."""

from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ms_dcr_benchmark_test_") as temp_dir:
        output_dir = Path(temp_dir)
        command = [
            sys.executable,
            str(ROOT / "scripts" / "benchmark_ms_dcr.py"),
            str(ROOT / "demo_data" / "demo_dda_32spectra.mzML"),
            "--repeats",
            "2",
            "--output-dir",
            str(output_dir),
        ]
        subprocess.run(command, cwd=ROOT, check=True)

        runs_path = output_dir / "ms_dcr_benchmark_runs.csv"
        summary_path = output_dir / "ms_dcr_benchmark_summary.csv"
        if not runs_path.is_file() or not summary_path.is_file():
            raise AssertionError("Benchmark CSV files were not created")

        with runs_path.open(newline="", encoding="utf-8") as handle:
            runs = list(csv.DictReader(handle))
        with summary_path.open(newline="", encoding="utf-8") as handle:
            summaries = list(csv.DictReader(handle))

        if len(runs) != 2:
            raise AssertionError(f"Expected 2 run records, observed {len(runs)}")
        if len(summaries) != 1 or summaries[0]["runs"] != "2":
            raise AssertionError("Benchmark summary does not report two runs")
        if any(int(row["spectra_count"]) != 32 for row in runs):
            raise AssertionError("Unexpected decoded spectrum count")

    print("MS-DCR benchmark smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

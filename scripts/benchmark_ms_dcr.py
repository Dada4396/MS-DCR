#!/usr/bin/env python3
"""Run repeatable MS-DCR encoding and decoding benchmarks.

The script records every timed run and writes both run-level and summary CSV
files. Timing uses ``time.perf_counter`` and throughput uses decimal MB
(1 MB = 1,000,000 bytes).
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ms_dcr.core import (  # noqa: E402
    DEFAULT_BLOCK_SIZE,
    DEFAULT_DECIMAL_PLACES,
    DEFAULT_T_MIN,
    DEFAULT_T_SIM,
    MSDCRConfig,
    MSDCREngine,
    infer_acquisition_mode,
)

RUN_COLUMNS = [
    "file",
    "acquisition_mode",
    "run",
    "input_bytes",
    "output_bytes",
    "compression_ratio",
    "encode_seconds",
    "decode_seconds",
    "encode_MB_per_s",
    "decode_MB_per_s",
    "spectra_count",
    "path_A_blocks",
    "path_B_blocks",
]

SUMMARY_COLUMNS = [
    "file",
    "acquisition_mode",
    "runs",
    "input_bytes",
    "mean_output_bytes",
    "mean_compression_ratio",
    "mean_encode_seconds",
    "sd_encode_seconds",
    "mean_decode_seconds",
    "sd_decode_seconds",
    "mean_encode_MB_per_s",
    "sd_encode_MB_per_s",
    "mean_decode_MB_per_s",
    "sd_decode_MB_per_s",
    "spectra_count",
    "path_A_blocks",
    "path_B_blocks",
]


def _mean(values: Iterable[float]) -> float:
    return statistics.fmean(values)


def _sd(values: Sequence[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def _write_csv(path: Path, columns: Sequence[str], rows: Sequence[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def benchmark_file(
    input_path: Path,
    repeats: int,
    acquisition_mode: str,
    decimal_places: int,
    block_size: int,
    t_min: int,
    t_sim: float,
) -> List[Dict[str, object]]:
    """Benchmark one mzML file and return run-level records."""

    input_path = input_path.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if repeats < 1:
        raise ValueError("--repeats must be at least 1")

    mode = infer_acquisition_mode(input_path, acquisition_mode)
    config = MSDCRConfig(
        decimal_places=decimal_places,
        block_size=block_size,
        t_min=t_min,
        t_sim=t_sim,
        acquisition_mode=mode,
    )
    input_bytes = input_path.stat().st_size
    records: List[Dict[str, object]] = []

    with tempfile.TemporaryDirectory(prefix="ms_dcr_benchmark_") as temp_dir:
        temp_root = Path(temp_dir)
        for run_number in range(1, repeats + 1):
            encoded_path = temp_root / f"run_{run_number}.msdcr"
            restored_path = temp_root / f"run_{run_number}.restored.mzML"

            engine = MSDCREngine(config)
            encode_start = time.perf_counter()
            encode_result = engine.compress(input_path, encoded_path)
            encode_seconds = time.perf_counter() - encode_start

            decode_start = time.perf_counter()
            decode_result = MSDCREngine().decompress(encoded_path, restored_path)
            decode_seconds = time.perf_counter() - decode_start

            expected_count = int(encode_result["spectra_count"])
            observed_count = int(decode_result["spectra_count"])
            if observed_count != expected_count:
                raise RuntimeError(
                    f"Round-trip spectrum-count mismatch for {input_path.name}: "
                    f"{expected_count} encoded, {observed_count} decoded"
                )
            if not restored_path.is_file() or restored_path.stat().st_size == 0:
                raise RuntimeError(f"Round-trip output was not created for {input_path.name}")

            block_summaries = list(encode_result.get("block_summaries", []))
            path_a_blocks = sum(item.get("path") == "A" for item in block_summaries)
            path_b_blocks = sum(item.get("path") == "B" for item in block_summaries)
            output_bytes = encoded_path.stat().st_size

            records.append(
                {
                    "file": input_path.name,
                    "acquisition_mode": mode,
                    "run": run_number,
                    "input_bytes": input_bytes,
                    "output_bytes": output_bytes,
                    "compression_ratio": output_bytes / input_bytes,
                    "encode_seconds": encode_seconds,
                    "decode_seconds": decode_seconds,
                    "encode_MB_per_s": input_bytes / 1_000_000 / encode_seconds,
                    "decode_MB_per_s": input_bytes / 1_000_000 / decode_seconds,
                    "spectra_count": expected_count,
                    "path_A_blocks": path_a_blocks,
                    "path_B_blocks": path_b_blocks,
                }
            )

    return records


def summarize(records: Sequence[Dict[str, object]]) -> Dict[str, object]:
    """Summarize repeated benchmark records for one input file."""

    if not records:
        raise ValueError("No benchmark records to summarize")

    numeric = lambda key: [float(record[key]) for record in records]
    first = records[0]
    return {
        "file": first["file"],
        "acquisition_mode": first["acquisition_mode"],
        "runs": len(records),
        "input_bytes": int(first["input_bytes"]),
        "mean_output_bytes": _mean(numeric("output_bytes")),
        "mean_compression_ratio": _mean(numeric("compression_ratio")),
        "mean_encode_seconds": _mean(numeric("encode_seconds")),
        "sd_encode_seconds": _sd(numeric("encode_seconds")),
        "mean_decode_seconds": _mean(numeric("decode_seconds")),
        "sd_decode_seconds": _sd(numeric("decode_seconds")),
        "mean_encode_MB_per_s": _mean(numeric("encode_MB_per_s")),
        "sd_encode_MB_per_s": _sd(numeric("encode_MB_per_s")),
        "mean_decode_MB_per_s": _mean(numeric("decode_MB_per_s")),
        "sd_decode_MB_per_s": _sd(numeric("decode_MB_per_s")),
        "spectra_count": int(first["spectra_count"]),
        "path_A_blocks": int(first["path_A_blocks"]),
        "path_B_blocks": int(first["path_B_blocks"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark MS-DCR encoding and decoding with run-level output"
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="Input mzML files")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("benchmark_results"),
        help="Directory for run-level and summary CSV files",
    )
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--acquisition-mode", choices=["auto", "dda", "dia"], default="auto")
    parser.add_argument("--decimal-places", type=int, default=DEFAULT_DECIMAL_PLACES)
    parser.add_argument("--block-size", type=int, default=DEFAULT_BLOCK_SIZE)
    parser.add_argument("--t-min", type=int, default=DEFAULT_T_MIN)
    parser.add_argument("--t-sim", type=float, default=DEFAULT_T_SIM)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    all_records: List[Dict[str, object]] = []
    summaries: List[Dict[str, object]] = []

    for input_path in args.inputs:
        records = benchmark_file(
            input_path=input_path,
            repeats=args.repeats,
            acquisition_mode=args.acquisition_mode,
            decimal_places=args.decimal_places,
            block_size=args.block_size,
            t_min=args.t_min,
            t_sim=args.t_sim,
        )
        all_records.extend(records)
        summaries.append(summarize(records))

    output_dir = args.output_dir.resolve()
    run_path = output_dir / "ms_dcr_benchmark_runs.csv"
    summary_path = output_dir / "ms_dcr_benchmark_summary.csv"
    _write_csv(run_path, RUN_COLUMNS, all_records)
    _write_csv(summary_path, SUMMARY_COLUMNS, summaries)

    print(f"Wrote {run_path}")
    print(f"Wrote {summary_path}")
    for item in summaries:
        print(
            f"{item['file']}: ratio={item['mean_compression_ratio']:.4f}, "
            f"encode={item['mean_encode_MB_per_s']:.2f} MB/s, "
            f"decode={item['mean_decode_MB_per_s']:.2f} MB/s, "
            f"n={item['runs']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

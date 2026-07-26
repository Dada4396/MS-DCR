# Reproducibility Notes

## Environment

Tested with:

- Python 3.8+
- NumPy
- lxml
- zstandard

Install dependencies:

```bash
pip install -r requirements.txt
pip install -e .
```

## Smoke test

Run:

```bash
python tests/smoke_test.py
```

Expected output:

```text
MS-DCR smoke tests passed
```

The smoke test compresses and decompresses both demo mzML files and checks that the spectrum count is preserved.

## Repeated benchmark

Run the benchmark utility with the two demo files:

```bash
python scripts/benchmark_ms_dcr.py \
  demo_data/demo_dda_32spectra.mzML \
  demo_data/demo_dia_32spectra.mzML \
  --repeats 10 \
  --output-dir benchmark_results
```

The command creates:

- `ms_dcr_benchmark_runs.csv`, containing one row per timed run; and
- `ms_dcr_benchmark_summary.csv`, containing means and sample standard deviations.

Every run checks that the encoded and decoded spectrum counts agree. Timing
uses a monotonic high-resolution clock, and throughput is calculated from the
input mzML size using 1 MB = 1,000,000 bytes.

## Reported experimental environment

The manuscript timing experiments were performed on a Windows 10 workstation
with an Intel Core i3-12100F processor and 16 GB RAM. Each timing measurement
was repeated 10 times.

Downstream analyses used MaxQuant 2.7.5.0 and PEAKS Studio 13.1 for DDA data,
and DIA-NN 2.3.2 and Spectronaut 20.3 for DIA data.

## Scope

This repository verifies the MS-DCR routing, codec and round-trip workflow and
provides a standard runner for new timing experiments. Large benchmark files
and third-party downstream software are distributed through their respective
data repositories and vendors.

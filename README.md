# MS-DCR

**MS-DCR** is a reference implementation of adaptive compression routing for heterogeneous mass spectrometry (MS) data.

MS-DCR evaluates each mzML data block and routes it to one of two compression paths:

- **Path A, stacked compression** for blocks that pass the minimum-count and Jaccard-similarity gates.
- **Path B, independent compression** for small, heterogeneous or low-similarity blocks.

The repository provides mzML parsing, adaptive block routing, Zstandard wrapping, round-trip export, demonstration data, tests and a repeatable benchmark utility.

## Repository contents

```text
MS-DCR/
  ms_dcr.py                     # source-checkout CLI entry point
  src/ms_dcr/                   # installable Python package
  demo_data/                    # small DDA/DIA mzML demo subsets
  examples/run_demo.py          # end-to-end demo script
  scripts/extract_mzml_demo.py  # helper for making small demo mzML files
  scripts/benchmark_ms_dcr.py    # repeated encode/decode benchmark runner
  tests/smoke_test.py           # round-trip smoke test
  docs/                         # data, provenance and reproducibility notes
  CITATION.cff                  # citation metadata
```

## Installation

Python 3.8 or later is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

You can also run MS-DCR directly from a source checkout without installing the package:

```bash
python ms_dcr.py --help
python -m ms_dcr --help
```

## Quick start

Compress the demo DIA file:

```bash
ms-dcr compress \
  -i demo_data/demo_dia_32spectra.mzML \
  -o demo_data/demo_dia_32spectra.msdcr \
  --acquisition-mode dia
```

Inspect the MS-DCR metadata:

```bash
ms-dcr inspect \
  -i demo_data/demo_dia_32spectra.msdcr
```

Decompress to a minimal mzML file:

```bash
ms-dcr decompress \
  -i demo_data/demo_dia_32spectra.msdcr \
  -o demo_data/demo_dia_32spectra.restored.mzML
```

Run the smoke test:

```bash
python tests/smoke_test.py
```

Run the complete demo script:

```bash
python examples/run_demo.py
```

Run a 10-repeat benchmark and export run-level and summary CSV files:

```bash
python scripts/benchmark_ms_dcr.py \
  demo_data/demo_dda_32spectra.mzML \
  demo_data/demo_dia_32spectra.mzML \
  --repeats 10 \
  --output-dir benchmark_results
```

The benchmark verifies the decoded spectrum count on every run. Throughput is
reported in decimal MB/s and summary files include the arithmetic mean and
sample standard deviation.

## Core algorithmic scope

This release focuses on the central MS-DCR codec path:

1. mzML spectrum parsing;
2. block-level routing using `T_min` and Jaccard similarity;
3. adaptive stacked encoding with tag arrays;
4. independent safe-path encoding;
5. Zstd compression of block payloads;
6. minimal mzML export for round-trip reproducibility checks.

Downstream identification and quantification were performed with established
proteomics applications and are described in the associated manuscript.

## Demo data

The included demo files are small mzML subsets extracted from original DDA and DIA data:

- `demo_data/demo_dia_32spectra.mzML`
- `demo_data/demo_dda_32spectra.mzML`

They are included only to make the core release runnable without multi-GB data downloads.

## Citation

Versioned archives are preserved through the GitHub releases linked to Zenodo.

## License

This repository is released under the MIT License.

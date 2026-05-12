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

## Limitations of the core release

This repository verifies the core codec and routing behavior. It does not reproduce every manuscript figure. Full figure reproduction would require:

- complete raw benchmark data;
- exact benchmark parameter files;
- external tools used in the manuscript;
- downstream search-engine configurations; and
- plotting scripts for each manuscript figure.

These can be added as a separate reproducibility workflow if required by reviewers.

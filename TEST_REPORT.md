# Test Report

Date: 2026-07-26

The repository was tested locally with the dependencies listed in `requirements.txt`.

Commands run:

```bash
python tests/smoke_test.py
python tests/benchmark_smoke_test.py
python examples/run_demo.py
python ms_dcr.py --help
```

Expected smoke-test output:

```text
MS-DCR smoke tests passed
```

The smoke test compresses and decompresses both demo mzML files and checks that the spectrum count is preserved.

The benchmark smoke test performs two timed encode/decode repetitions, checks
the decoded spectrum count and validates the run-level and summary CSV files.
The manuscript benchmark command uses `--repeats 10`.

Generated `.msdcr` and restored `.mzML` files are ignored by Git and should not be committed unless they are intentionally added as release artifacts.

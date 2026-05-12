# Test Report

Date: 2026-05-12

The repository was tested locally with the dependencies listed in `requirements.txt`.

Commands run:

```bash
python tests/smoke_test.py
python examples/run_demo.py
python ms_dcr.py --help
```

Expected smoke-test output:

```text
MS-DCR smoke tests passed
```

The smoke test compresses and decompresses both demo mzML files and checks that the spectrum count is preserved.

Generated `.msdcr` and restored `.mzML` files are ignored by Git and should not be committed unless they are intentionally added as release artifacts.

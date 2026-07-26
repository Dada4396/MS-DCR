# GitHub Release Checklist

Use this checklist when preparing the next MS-DCR release.

## Repository

- Use the public repository at `https://github.com/Dada4396/MS-DCR`.
- Push the reviewed `main` branch after all tests pass.
- Confirm that the README quick-start commands work on a fresh clone.
- Confirm that `python tests/smoke_test.py` passes after `pip install -e .`.
- Confirm that `python tests/benchmark_smoke_test.py` passes.

## Release

- Choose the next version tag after the existing `v1.0.0` release.
- Attach a ZIP or source archive only if GitHub does not generate one automatically.
- Confirm that `CITATION.cff` renders correctly in GitHub's citation widget.
- Keep the GitHub repository linked to Zenodo and archive the new release.
- Update the manuscript citation if the new release receives a version-specific DOI.

## Manuscript wording

Recommended availability sentence:

> Source code, documentation, benchmark utilities and demo mzML files for MS-DCR are available at `https://github.com/Dada4396/MS-DCR`. The archived v1.1.0 release is available at `https://doi.org/10.5281/zenodo.21608786`.

## Before the next release

- Confirm the creator and contributor metadata in `CITATION.cff` and Zenodo.
- Confirm that demo data can be publicly redistributed.
- Confirm that MIT licensing is acceptable to all authors and your institution.

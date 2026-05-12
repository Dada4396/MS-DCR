# GitHub Release Checklist

Use this checklist before submitting the manuscript to a software-oriented journal.

## Repository

- Create a public GitHub repository named `MS-DCR`.
- Push the local `main` branch to `https://github.com/Dada4396/MS-DCR`.
- Confirm that the README quick-start commands work on a fresh clone.
- Confirm that `python tests/smoke_test.py` passes after `pip install -e .`.

## Release

- Create a GitHub release named `v1.0.0`.
- Attach a ZIP or source archive only if GitHub does not generate one automatically.
- Confirm that `CITATION.cff` renders correctly in GitHub's citation widget.
- Bind the GitHub repository to Zenodo and archive the `v1.0.0` release.
- Replace the placeholder Zenodo DOI in the manuscript after the DOI is available.

## Manuscript wording

Recommended availability sentence:

> Source code, documentation and demo mzML files for MS-DCR are available at `https://github.com/Dada4396/MS-DCR`. The archived release used in this manuscript is available at `[Zenodo DOI to be added before submission]`.

## Before public release

- Replace placeholder authors in `CITATION.cff`.
- Confirm that demo data can be publicly redistributed.
- Confirm that MIT licensing is acceptable to all authors and your institution.

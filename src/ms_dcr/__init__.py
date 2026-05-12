"""MS-DCR: adaptive compression routing for mass spectrometry data."""

from .core import (
    MSDCRConfig,
    MSDCREngine,
    Spectrum,
    extract_demo_mzml,
    infer_acquisition_mode,
    iter_mzml_spectra,
    main,
    read_mzml,
    write_minimal_mzml,
)

__all__ = [
    "MSDCRConfig",
    "MSDCREngine",
    "Spectrum",
    "extract_demo_mzml",
    "infer_acquisition_mode",
    "iter_mzml_spectra",
    "main",
    "read_mzml",
    "write_minimal_mzml",
]

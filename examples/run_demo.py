#!/usr/bin/env python3
"""Run a minimal MS-DCR compression/decompression demo."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ms_dcr import MSDCRConfig, MSDCREngine  # noqa: E402


def main() -> int:
    demo = ROOT / "demo_data" / "demo_dia_32spectra.mzML"
    compressed = ROOT / "demo_data" / "demo_dia_32spectra.msdcr"
    restored = ROOT / "demo_data" / "demo_dia_32spectra.restored.mzML"

    engine = MSDCREngine(MSDCRConfig(acquisition_mode="dia"))
    metadata = engine.compress(demo, compressed)
    print("Compressed:", metadata["output_bytes"], "bytes")

    result = MSDCREngine().decompress(compressed, restored)
    print("Restored spectra:", result["spectra_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

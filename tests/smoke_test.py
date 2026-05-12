#!/usr/bin/env python3
"""Smoke test for the MS-DCR core release."""

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ms_dcr import MSDCRConfig, MSDCREngine, read_mzml


def run_one(input_path: Path, acquisition_mode: str) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        compressed = temp_dir / (input_path.stem + ".msdcr")
        restored = temp_dir / (input_path.stem + ".restored.mzML")

        engine = MSDCREngine(MSDCRConfig(block_size=16, t_min=4, t_sim=0.10, acquisition_mode=acquisition_mode))
        meta = engine.compress(input_path, compressed)
        assert compressed.exists() and compressed.stat().st_size > 0

        result = MSDCREngine().decompress(compressed, restored)
        assert restored.exists() and restored.stat().st_size > 0

        original_count = len(read_mzml(input_path))
        restored_count = len(read_mzml(restored))
        assert original_count == restored_count == result["spectra_count"]
        assert meta["spectra_count"] == original_count


def main() -> int:
    demo_dir = ROOT / "demo_data"
    run_one(demo_dir / "demo_dia_32spectra.mzML", "dia")
    run_one(demo_dir / "demo_dda_32spectra.mzML", "dda")
    print("MS-DCR smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

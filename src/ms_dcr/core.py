#!/usr/bin/env python3
"""Core implementation of the MS-DCR.

This module is a compact, reviewer-oriented implementation of the central MS-DCR
ideas described in the manuscript:

* stream mzML spectra;
* route blocks with spectrum-count and Jaccard-similarity gates;
* encode similar blocks with a stacked tag-array path;
* encode heterogeneous or small blocks independently;
* wrap block payloads with Zstandard compression; and
* export a minimal mzML file for round-trip checks.

The implementation is intentionally self-contained. It is not a full replacement
for vendor converters or the complete experimental pipeline used for the paper.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import struct
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np
import zstandard as zstd
from lxml import etree

VERSION = "1.0.0"
MAGIC = b"MSD1"
MZML_NS = "http://psi.hupo.org/ms/mzml"
NS = {"ms": MZML_NS}

MS_LEVEL_ACCESSION = "MS:1000511"
MZ_ARRAY_ACCESSIONS = {"MS:1000514", "MS:1000827"}
INTENSITY_ARRAY_ACCESSIONS = {"MS:1000515", "MS:1000828"}
ZLIB_ACCESSION = "MS:1000574"
NO_COMPRESSION_ACCESSION = "MS:1000576"
FLOAT32_ACCESSION = "MS:1000521"
FLOAT64_ACCESSION = "MS:1000523"
SCAN_START_TIME_ACCESSION = "MS:1000016"
MINUTE_ACCESSION = "UO:0000031"
SECOND_ACCESSION = "UO:0000010"

DEFAULT_DECIMAL_PLACES = 6
DEFAULT_BLOCK_SIZE = 256
DEFAULT_T_MIN = 16
DEFAULT_T_SIM = 0.60
DEFAULT_DDA_TARGET = 6
DEFAULT_DIA_TARGET = 8
DEFAULT_ZSTD_LEVEL = 9
DEFAULT_SIMILARITY_BIN_DP = 1


@dataclass
class Spectrum:
    """Minimal spectrum representation used by the MS-DCR core codec."""

    spectrum_id: str
    index: int
    ms_level: int
    retention_time_min: float
    mz: np.ndarray
    intensity: np.ndarray

    def normalized(self) -> "Spectrum":
        """Return a length-matched, m/z-sorted copy."""

        mz = np.asarray(self.mz, dtype=np.float64)
        intensity = np.asarray(self.intensity, dtype=np.float64)
        if len(mz) != len(intensity):
            n = min(len(mz), len(intensity))
            mz = mz[:n]
            intensity = intensity[:n]
        if len(mz) > 1:
            order = np.argsort(mz, kind="mergesort")
            mz = mz[order]
            intensity = intensity[order]
        return Spectrum(
            spectrum_id=self.spectrum_id,
            index=self.index,
            ms_level=self.ms_level,
            retention_time_min=self.retention_time_min,
            mz=mz,
            intensity=intensity,
        )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _cv_accessions(element: etree._Element) -> set[str]:
    return {cv.get("accession", "") for cv in element.xpath("./ms:cvParam", namespaces=NS)}


def _cv_name(element: etree._Element, accession: str) -> Optional[str]:
    cv = element.xpath(f'./ms:cvParam[@accession="{accession}"]', namespaces=NS)
    if not cv:
        return None
    return cv[0].get("name")


def _array_kind(binary_data_array: etree._Element) -> Optional[str]:
    accessions = _cv_accessions(binary_data_array)
    if accessions & MZ_ARRAY_ACCESSIONS:
        return "mz"
    if accessions & INTENSITY_ARRAY_ACCESSIONS:
        return "intensity"
    names = {cv.get("name", "").lower() for cv in binary_data_array.xpath("./ms:cvParam", namespaces=NS)}
    if "m/z array" in names or "mass-to-charge ratio array" in names:
        return "mz"
    if "intensity array" in names or "signal intensity array" in names:
        return "intensity"
    return None


def decode_binary_array(binary_data_array: etree._Element) -> np.ndarray:
    """Decode an mzML binaryDataArray into a NumPy float array."""

    binary_node = binary_data_array.find(f"{{{MZML_NS}}}binary")
    if binary_node is None or not (binary_node.text or "").strip():
        return np.array([], dtype=np.float64)

    accessions = _cv_accessions(binary_data_array)
    raw = base64.b64decode(binary_node.text.strip())
    if ZLIB_ACCESSION in accessions:
        raw = zlib.decompress(raw)

    dtype = np.dtype("<f8")
    if FLOAT32_ACCESSION in accessions:
        dtype = np.dtype("<f4")
    elif FLOAT64_ACCESSION in accessions:
        dtype = np.dtype("<f8")
    elif len(raw) % 8 == 0:
        dtype = np.dtype("<f8")
    elif len(raw) % 4 == 0:
        dtype = np.dtype("<f4")
    else:
        raise ValueError(f"Unsupported binary array length: {len(raw)} bytes")

    return np.frombuffer(raw, dtype=dtype).astype(np.float64, copy=False)


def parse_spectrum(spectrum_node: etree._Element) -> Spectrum:
    """Parse one mzML spectrum element."""

    spectrum_id = spectrum_node.get("id") or f"spectrum_{spectrum_node.get('index', 'unknown')}"
    index = int(spectrum_node.get("index", "0"))

    ms_level = 1
    ms_level_nodes = spectrum_node.xpath(f'./ms:cvParam[@accession="{MS_LEVEL_ACCESSION}"]', namespaces=NS)
    if ms_level_nodes:
        try:
            ms_level = int(float(ms_level_nodes[0].get("value", "1")))
        except ValueError:
            ms_level = 1

    retention_time_min = 0.0
    rt_nodes = spectrum_node.xpath(
        f'.//ms:scan/ms:cvParam[@accession="{SCAN_START_TIME_ACCESSION}"]',
        namespaces=NS,
    )
    if rt_nodes:
        try:
            retention_time_min = float(rt_nodes[0].get("value", "0"))
            unit = rt_nodes[0].get("unitAccession", "")
            if unit == SECOND_ACCESSION:
                retention_time_min /= 60.0
        except ValueError:
            retention_time_min = 0.0

    mz = np.array([], dtype=np.float64)
    intensity = np.array([], dtype=np.float64)
    for binary_data_array in spectrum_node.xpath(".//ms:binaryDataArray", namespaces=NS):
        kind = _array_kind(binary_data_array)
        if kind is None:
            continue
        values = decode_binary_array(binary_data_array)
        if kind == "mz":
            mz = values
        elif kind == "intensity":
            intensity = values

    return Spectrum(
        spectrum_id=spectrum_id,
        index=index,
        ms_level=ms_level,
        retention_time_min=retention_time_min,
        mz=mz,
        intensity=intensity,
    ).normalized()


def iter_mzml_spectra(path: Path, limit: Optional[int] = None) -> Iterator[Spectrum]:
    """Yield spectra from an mzML or indexedmzML file using streaming parsing."""

    count = 0
    context = etree.iterparse(str(path), events=("end",), recover=True, huge_tree=True)
    for _, element in context:
        if _local_name(element.tag) != "spectrum":
            continue
        yield parse_spectrum(element)
        count += 1
        element.clear()
        while element.getprevious() is not None:
            del element.getparent()[0]
        if limit is not None and count >= limit:
            break


def read_mzml(path: Path, limit: Optional[int] = None) -> List[Spectrum]:
    return list(iter_mzml_spectra(path, limit=limit))


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))


def _smallest_signed_dtype(values: np.ndarray) -> np.dtype:
    if values.size == 0:
        return np.dtype("<i2")
    min_value = int(values.min())
    max_value = int(values.max())
    if np.iinfo(np.int16).min <= min_value and max_value <= np.iinfo(np.int16).max:
        return np.dtype("<i2")
    if np.iinfo(np.int32).min <= min_value and max_value <= np.iinfo(np.int32).max:
        return np.dtype("<i4")
    return np.dtype("<i8")


def _smallest_unsigned_dtype(values: np.ndarray) -> np.dtype:
    if values.size == 0 or int(values.max(initial=0)) <= np.iinfo(np.uint8).max:
        return np.dtype("u1")
    if int(values.max()) <= np.iinfo(np.uint16).max:
        return np.dtype("<u2")
    return np.dtype("<u4")


def quantize_mz(mz: np.ndarray, decimal_places: int) -> np.ndarray:
    scale = 10**decimal_places
    return np.rint(np.asarray(mz, dtype=np.float64) * scale).astype(np.int64)


def dequantize_mz(mz_quantized: np.ndarray, decimal_places: int) -> np.ndarray:
    scale = 10**decimal_places
    return np.asarray(mz_quantized, dtype=np.float64) / scale


def encode_int_delta(values: np.ndarray, reference: int = 0) -> Dict[str, object]:
    """Encode integer values as deltas from a reference and previous value."""

    values = np.asarray(values, dtype=np.int64)
    if values.size == 0:
        dtype = np.dtype("<i2")
        payload = np.array([], dtype=dtype)
    else:
        shifted = values.copy()
        shifted[0] -= reference
        if shifted.size > 1:
            shifted[1:] = values[1:] - values[:-1]
        dtype = _smallest_signed_dtype(shifted)
        payload = shifted.astype(dtype)
    return {"dtype": dtype.str, "data": _b64(payload.tobytes()), "count": int(values.size), "reference": int(reference)}


def decode_int_delta(payload: Dict[str, object]) -> np.ndarray:
    dtype = np.dtype(str(payload["dtype"]))
    count = int(payload.get("count", 0))
    if count == 0:
        return np.array([], dtype=np.int64)
    delta = np.frombuffer(_unb64(str(payload["data"])), dtype=dtype).astype(np.int64)
    if delta.size != count:
        raise ValueError(f"Delta payload count mismatch: expected {count}, observed {delta.size}")
    values = np.empty_like(delta, dtype=np.int64)
    values[0] = int(payload.get("reference", 0)) + delta[0]
    if count > 1:
        values[1:] = np.cumsum(delta[1:]) + values[0]
    return values


def encode_float64(values: np.ndarray) -> Dict[str, object]:
    values = np.asarray(values, dtype="<f8")
    return {"dtype": "<f8", "data": _b64(values.tobytes()), "count": int(values.size)}


def decode_float64(payload: Dict[str, object]) -> np.ndarray:
    values = np.frombuffer(_unb64(str(payload["data"])), dtype=np.dtype(str(payload["dtype"]))).astype(np.float64)
    expected = int(payload.get("count", values.size))
    if values.size != expected:
        raise ValueError(f"Float payload count mismatch: expected {expected}, observed {values.size}")
    return values


def spectrum_signature(spectrum: Spectrum, bin_decimals: int = DEFAULT_SIMILARITY_BIN_DP) -> set[int]:
    if spectrum.mz.size == 0:
        return set()
    quantized = np.rint(spectrum.mz * (10**bin_decimals)).astype(np.int64)
    return set(int(x) for x in quantized)


def mean_adjacent_jaccard(spectra: Sequence[Spectrum], bin_decimals: int = DEFAULT_SIMILARITY_BIN_DP) -> float:
    if len(spectra) < 2:
        return 0.0
    scores: List[float] = []
    previous = spectrum_signature(spectra[0], bin_decimals)
    for spectrum in spectra[1:]:
        current = spectrum_signature(spectrum, bin_decimals)
        if not previous and not current:
            scores.append(1.0)
        elif not previous or not current:
            scores.append(0.0)
        else:
            scores.append(len(previous & current) / len(previous | current))
        previous = current
    return float(np.mean(scores)) if scores else 0.0


def infer_acquisition_mode(path: Optional[Path], explicit: str = "auto") -> str:
    if explicit in {"dda", "dia"}:
        return explicit
    name = str(path or "").lower()
    if "dia" in name:
        return "dia"
    if "dda" in name:
        return "dda"
    return "auto"


@dataclass
class MSDCRConfig:
    decimal_places: int = DEFAULT_DECIMAL_PLACES
    block_size: int = DEFAULT_BLOCK_SIZE
    t_min: int = DEFAULT_T_MIN
    t_sim: float = DEFAULT_T_SIM
    dda_target: int = DEFAULT_DDA_TARGET
    dia_target: int = DEFAULT_DIA_TARGET
    zstd_level: int = DEFAULT_ZSTD_LEVEL
    similarity_bin_decimals: int = DEFAULT_SIMILARITY_BIN_DP
    acquisition_mode: str = "auto"

    def as_dict(self) -> Dict[str, object]:
        return {
            "decimal_places": self.decimal_places,
            "block_size": self.block_size,
            "t_min": self.t_min,
            "t_sim": self.t_sim,
            "dda_target": self.dda_target,
            "dia_target": self.dia_target,
            "zstd_level": self.zstd_level,
            "similarity_bin_decimals": self.similarity_bin_decimals,
            "acquisition_mode": self.acquisition_mode,
        }


class MSDCREngine:
    """Adaptive compression engine for reviewer-scale MS-DCR files."""

    def __init__(self, config: Optional[MSDCRConfig] = None):
        self.config = config or MSDCRConfig()
        self.cctx = zstd.ZstdCompressor(level=self.config.zstd_level)
        self.dctx = zstd.ZstdDecompressor()

    def _target_stack_size(self, block: Sequence[Spectrum]) -> int:
        ms_level = block[0].ms_level if block else 1
        if ms_level == 1 or self.config.acquisition_mode == "dia":
            exponent = self.config.dia_target
        else:
            exponent = self.config.dda_target
        return max(1, min(2**exponent, len(block)))

    def _route_block(self, block: Sequence[Spectrum]) -> Tuple[str, float, str]:
        if len(block) < self.config.t_min:
            return "B", 0.0, "below_t_min"
        similarity = mean_adjacent_jaccard(block, self.config.similarity_bin_decimals)
        if similarity < self.config.t_sim:
            return "B", similarity, "below_t_sim"
        return "A", similarity, "passed"

    def _encode_independent_spectrum(self, spectrum: Spectrum) -> Dict[str, object]:
        mz_q = quantize_mz(spectrum.mz, self.config.decimal_places)
        return {
            "id": spectrum.spectrum_id,
            "index": spectrum.index,
            "ms_level": spectrum.ms_level,
            "rt_min": spectrum.retention_time_min,
            "mz": encode_int_delta(mz_q, reference=0),
            "intensity": encode_float64(spectrum.intensity),
        }

    def _decode_independent_spectrum(self, payload: Dict[str, object]) -> Spectrum:
        mz_q = decode_int_delta(payload["mz"])
        intensity = decode_float64(payload["intensity"])
        return Spectrum(
            spectrum_id=str(payload["id"]),
            index=int(payload["index"]),
            ms_level=int(payload["ms_level"]),
            retention_time_min=float(payload.get("rt_min", 0.0)),
            mz=dequantize_mz(mz_q, self.config.decimal_places),
            intensity=intensity,
        ).normalized()

    def _encode_substack(self, spectra: Sequence[Spectrum], reference_mz_q: int) -> Dict[str, object]:
        records: List[Tuple[int, int, float]] = []
        metadata: List[Dict[str, object]] = []
        for local_index, spectrum in enumerate(spectra):
            metadata.append(
                {
                    "id": spectrum.spectrum_id,
                    "index": spectrum.index,
                    "ms_level": spectrum.ms_level,
                    "rt_min": spectrum.retention_time_min,
                }
            )
            mz_q = quantize_mz(spectrum.mz, self.config.decimal_places)
            for mz_value, intensity_value in zip(mz_q, spectrum.intensity):
                records.append((int(mz_value), local_index, float(intensity_value)))

        records.sort(key=lambda item: (item[0], item[1]))
        mz_values = np.array([item[0] for item in records], dtype=np.int64)
        tags_raw = np.array([item[1] for item in records], dtype=np.uint32)
        intensities = np.array([item[2] for item in records], dtype=np.float64)
        tag_dtype = _smallest_unsigned_dtype(tags_raw)

        return {
            "spectra": metadata,
            "mz": encode_int_delta(mz_values, reference=reference_mz_q),
            "tag_dtype": tag_dtype.str,
            "tags": _b64(tags_raw.astype(tag_dtype).tobytes()),
            "tag_count": int(tags_raw.size),
            "intensity": encode_float64(intensities),
        }

    def _decode_substack(self, payload: Dict[str, object]) -> List[Spectrum]:
        metadata = list(payload["spectra"])
        mz_q = decode_int_delta(payload["mz"])
        tags = np.frombuffer(_unb64(str(payload["tags"])), dtype=np.dtype(str(payload["tag_dtype"]))).astype(np.int64)
        intensities = decode_float64(payload["intensity"])

        if not (mz_q.size == tags.size == intensities.size):
            raise ValueError("Stacked payload arrays have inconsistent lengths")

        mz_lists: List[List[float]] = [[] for _ in metadata]
        intensity_lists: List[List[float]] = [[] for _ in metadata]
        mz_values = dequantize_mz(mz_q, self.config.decimal_places)
        for mz_value, tag, intensity in zip(mz_values, tags, intensities):
            if tag < 0 or tag >= len(metadata):
                raise ValueError(f"Tag index {tag} outside sub-stack size {len(metadata)}")
            mz_lists[int(tag)].append(float(mz_value))
            intensity_lists[int(tag)].append(float(intensity))

        spectra: List[Spectrum] = []
        for idx, info in enumerate(metadata):
            spectra.append(
                Spectrum(
                    spectrum_id=str(info["id"]),
                    index=int(info["index"]),
                    ms_level=int(info["ms_level"]),
                    retention_time_min=float(info.get("rt_min", 0.0)),
                    mz=np.array(mz_lists[idx], dtype=np.float64),
                    intensity=np.array(intensity_lists[idx], dtype=np.float64),
                ).normalized()
            )
        return spectra

    def _encode_block(self, block: Sequence[Spectrum], block_index: int, previous_reference_q: int) -> Tuple[Dict[str, object], int]:
        route, similarity, reason = self._route_block(block)
        block_payload: Dict[str, object] = {
            "block_index": block_index,
            "path": route,
            "route_reason": reason,
            "similarity": similarity,
            "ms_level": block[0].ms_level if block else 1,
            "spectra_count": len(block),
        }

        if route == "B":
            encoded = [self._encode_independent_spectrum(spectrum) for spectrum in block]
            block_payload["spectra"] = encoded
            if block:
                last = block[-1]
                last_q = quantize_mz(last.mz, self.config.decimal_places)
                previous_reference_q = int(last_q[-1]) if last_q.size else previous_reference_q
            return block_payload, previous_reference_q

        substack_size = self._target_stack_size(block)
        substacks: List[Dict[str, object]] = []
        reference = previous_reference_q
        for start in range(0, len(block), substack_size):
            substack = block[start : start + substack_size]
            encoded_substack = self._encode_substack(substack, reference)
            substacks.append(encoded_substack)
            mz_q = decode_int_delta(encoded_substack["mz"])
            if mz_q.size:
                reference = int(mz_q[-1])
        block_payload["substack_size"] = substack_size
        block_payload["substacks"] = substacks
        return block_payload, reference

    def _decode_block(self, block_payload: Dict[str, object]) -> List[Spectrum]:
        if block_payload["path"] == "B":
            return [self._decode_independent_spectrum(item) for item in block_payload.get("spectra", [])]
        spectra: List[Spectrum] = []
        for substack in block_payload.get("substacks", []):
            spectra.extend(self._decode_substack(substack))
        return spectra

    def compress(self, input_path: Path, output_path: Path, limit: Optional[int] = None) -> Dict[str, object]:
        input_path = Path(input_path)
        output_path = Path(output_path)
        start_time = time.time()
        spectra = read_mzml(input_path, limit=limit)
        if not spectra:
            raise ValueError(f"No spectra could be parsed from {input_path}")

        blocks = [spectra[i : i + self.config.block_size] for i in range(0, len(spectra), self.config.block_size)]
        previous_reference_q = 0
        compressed_blocks: List[bytes] = []
        block_summaries: List[Dict[str, object]] = []
        for block_index, block in enumerate(blocks):
            payload, previous_reference_q = self._encode_block(block, block_index, previous_reference_q)
            payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            compressed = self.cctx.compress(payload_bytes)
            compressed_blocks.append(compressed)
            block_summaries.append(
                {
                    "block_index": block_index,
                    "path": payload["path"],
                    "reason": payload["route_reason"],
                    "similarity": round(float(payload["similarity"]), 4),
                    "spectra_count": payload["spectra_count"],
                    "compressed_bytes": len(compressed),
                }
            )

        metadata = {
            "format": "MS-DCR",
            "version": VERSION,
            "source_file": input_path.name,
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "config": self.config.as_dict(),
            "spectra_count": len(spectra),
            "blocks_count": len(blocks),
            "ms1_count": sum(1 for spectrum in spectra if spectrum.ms_level == 1),
            "ms2_count": sum(1 for spectrum in spectra if spectrum.ms_level == 2),
            "block_summaries": block_summaries,
        }
        metadata_bytes = self.cctx.compress(json.dumps(metadata, separators=(",", ":")).encode("utf-8"))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as handle:
            handle.write(MAGIC)
            handle.write(struct.pack("<I", len(metadata_bytes)))
            handle.write(metadata_bytes)
            handle.write(struct.pack("<Q", len(compressed_blocks)))
            for block in compressed_blocks:
                handle.write(struct.pack("<Q", len(block)))
                handle.write(block)

        elapsed = time.time() - start_time
        metadata["input_bytes"] = input_path.stat().st_size
        metadata["output_bytes"] = output_path.stat().st_size
        metadata["compression_ratio"] = round(output_path.stat().st_size / input_path.stat().st_size, 6)
        metadata["elapsed_seconds"] = round(elapsed, 3)
        return metadata

    def read_dcr(self, input_path: Path) -> Tuple[Dict[str, object], List[Dict[str, object]]]:
        input_path = Path(input_path)
        with input_path.open("rb") as handle:
            magic = handle.read(4)
            if magic != MAGIC:
                raise ValueError(f"Invalid MS-DCR magic number: {magic!r}")
            meta_len = struct.unpack("<I", handle.read(4))[0]
            metadata = json.loads(self.dctx.decompress(handle.read(meta_len)).decode("utf-8"))
            block_count = struct.unpack("<Q", handle.read(8))[0]
            blocks = []
            for _ in range(block_count):
                block_len = struct.unpack("<Q", handle.read(8))[0]
                blocks.append(json.loads(self.dctx.decompress(handle.read(block_len)).decode("utf-8")))
        return metadata, blocks

    def decompress(self, input_path: Path, output_path: Path) -> Dict[str, object]:
        start_time = time.time()
        metadata, blocks = self.read_dcr(input_path)
        self.config = MSDCRConfig(**metadata["config"])
        spectra: List[Spectrum] = []
        for block in blocks:
            spectra.extend(self._decode_block(block))
        spectra.sort(key=lambda item: item.index)
        write_minimal_mzml(spectra, output_path, run_id=Path(metadata.get("source_file", "MS_MS_DCR_demo")).stem)
        return {
            "source_file": metadata.get("source_file"),
            "spectra_count": len(spectra),
            "output_file": str(output_path),
            "elapsed_seconds": round(time.time() - start_time, 3),
        }

    def inspect(self, input_path: Path) -> Dict[str, object]:
        metadata, _ = self.read_dcr(input_path)
        return metadata


def _cv(parent: etree._Element, accession: str, name: str, value: str = "", **attrs: str) -> etree._Element:
    data = {"cvRef": "MS", "accession": accession, "name": name, "value": value}
    data.update(attrs)
    return etree.SubElement(parent, f"{{{MZML_NS}}}cvParam", **data)


def _add_binary_array(parent: etree._Element, accession: str, name: str, values: np.ndarray) -> None:
    binary_array = etree.SubElement(parent, f"{{{MZML_NS}}}binaryDataArray", encodedLength="0")
    _cv(binary_array, NO_COMPRESSION_ACCESSION, "no compression")
    _cv(binary_array, FLOAT64_ACCESSION, "64-bit float")
    _cv(binary_array, accession, name, unitCvRef="MS", unitAccession="MS:1000040" if name == "m/z array" else "MS:1000131", unitName="m/z" if name == "m/z array" else "number of detector counts")
    binary = etree.SubElement(binary_array, f"{{{MZML_NS}}}binary")
    binary.text = base64.b64encode(np.asarray(values, dtype="<f8").tobytes()).decode("ascii")


def write_minimal_mzml(spectra: Sequence[Spectrum], output_path: Path, run_id: str = "MS_MS_DCR_demo") -> None:
    """Write a compact mzML file containing reconstructed mz/intensity arrays."""

    output_path = Path(output_path)
    nsmap = {None: MZML_NS, "xsi": "http://www.w3.org/2001/XMLSchema-instance"}
    root = etree.Element(f"{{{MZML_NS}}}mzML", nsmap=nsmap, id=run_id, version="1.1.0")
    cv_list = etree.SubElement(root, f"{{{MZML_NS}}}cvList", count="1")
    etree.SubElement(
        cv_list,
        f"{{{MZML_NS}}}cv",
        id="MS",
        fullName="Proteomics Standards Initiative Mass Spectrometry Ontology",
        version="4.1.136",
        URI="https://raw.githubusercontent.com/HUPO-PSI/psi-ms-CV/master/psi-ms.obo",
    )
    run = etree.SubElement(root, f"{{{MZML_NS}}}run", id=run_id)
    spectrum_list = etree.SubElement(run, f"{{{MZML_NS}}}spectrumList", count=str(len(spectra)))
    for out_index, spectrum in enumerate(spectra):
        spectrum = spectrum.normalized()
        element = etree.SubElement(
            spectrum_list,
            f"{{{MZML_NS}}}spectrum",
            index=str(out_index),
            id=spectrum.spectrum_id,
            defaultArrayLength=str(len(spectrum.mz)),
        )
        _cv(element, MS_LEVEL_ACCESSION, "ms level", str(spectrum.ms_level))
        scan_list = etree.SubElement(element, f"{{{MZML_NS}}}scanList", count="1")
        scan = etree.SubElement(scan_list, f"{{{MZML_NS}}}scan")
        _cv(
            scan,
            SCAN_START_TIME_ACCESSION,
            "scan start time",
            f"{spectrum.retention_time_min:.6f}",
            unitCvRef="UO",
            unitAccession=MINUTE_ACCESSION,
            unitName="minute",
        )
        binary_list = etree.SubElement(element, f"{{{MZML_NS}}}binaryDataArrayList", count="2")
        _add_binary_array(binary_list, "MS:1000514", "m/z array", spectrum.mz)
        _add_binary_array(binary_list, "MS:1000515", "intensity array", spectrum.intensity)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    etree.ElementTree(root).write(str(output_path), pretty_print=True, encoding="utf-8", xml_declaration=True)


def extract_demo_mzml(input_path: Path, output_path: Path, spectra_count: int) -> Dict[str, object]:
    spectra = read_mzml(Path(input_path), limit=spectra_count)
    if not spectra:
        raise ValueError(f"No spectra extracted from {input_path}")
    write_minimal_mzml(spectra, Path(output_path), run_id=Path(input_path).stem + f"_demo_{spectra_count}")
    return {
        "input": str(input_path),
        "output": str(output_path),
        "spectra_count": len(spectra),
        "ms1_count": sum(1 for spectrum in spectra if spectrum.ms_level == 1),
        "ms2_count": sum(1 for spectrum in spectra if spectrum.ms_level == 2),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MS-DCR core compressor")
    parser.add_argument("--version", action="version", version=f"MS-DCR core {VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_config(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--decimal-places", type=int, default=DEFAULT_DECIMAL_PLACES)
        sub.add_argument("--block-size", type=int, default=DEFAULT_BLOCK_SIZE)
        sub.add_argument("--t-min", type=int, default=DEFAULT_T_MIN)
        sub.add_argument("--t-sim", type=float, default=DEFAULT_T_SIM)
        sub.add_argument("--acquisition-mode", choices=["auto", "dda", "dia"], default="auto")

    compress = subparsers.add_parser("compress", help="Compress mzML to MS-DCR")
    compress.add_argument("-i", "--input", required=True, type=Path)
    compress.add_argument("-o", "--output", required=True, type=Path)
    compress.add_argument("--limit", type=int, default=None, help="Read only the first N spectra")
    add_common_config(compress)

    decompress = subparsers.add_parser("decompress", help="Decompress MS-DCR to a minimal mzML")
    decompress.add_argument("-i", "--input", required=True, type=Path)
    decompress.add_argument("-o", "--output", required=True, type=Path)

    inspect = subparsers.add_parser("inspect", help="Print MS-DCR metadata")
    inspect.add_argument("-i", "--input", required=True, type=Path)

    extract = subparsers.add_parser("extract-demo", help="Extract a small mzML demo file")
    extract.add_argument("-i", "--input", required=True, type=Path)
    extract.add_argument("-o", "--output", required=True, type=Path)
    extract.add_argument("-n", "--spectra-count", type=int, default=32)

    return parser


def config_from_args(args: argparse.Namespace) -> MSDCRConfig:
    input_path = getattr(args, "input", None)
    acquisition_mode = infer_acquisition_mode(input_path, getattr(args, "acquisition_mode", "auto"))
    return MSDCRConfig(
        decimal_places=getattr(args, "decimal_places", DEFAULT_DECIMAL_PLACES),
        block_size=getattr(args, "block_size", DEFAULT_BLOCK_SIZE),
        t_min=getattr(args, "t_min", DEFAULT_T_MIN),
        t_sim=getattr(args, "t_sim", DEFAULT_T_SIM),
        acquisition_mode=acquisition_mode,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "compress":
        engine = MSDCREngine(config_from_args(args))
        result = engine.compress(args.input, args.output, limit=args.limit)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "decompress":
        engine = MSDCREngine()
        result = engine.decompress(args.input, args.output)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "inspect":
        engine = MSDCREngine()
        print(json.dumps(engine.inspect(args.input), indent=2))
        return 0

    if args.command == "extract-demo":
        print(json.dumps(extract_demo_mzml(args.input, args.output, args.spectra_count), indent=2))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

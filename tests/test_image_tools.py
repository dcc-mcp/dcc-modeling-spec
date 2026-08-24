from __future__ import annotations

import struct
import zlib
from pathlib import Path

from conftest import load_script


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _write_png(
    path: Path, width: int, height: int, rgb: tuple[int, int, int], *, gamma: float | None = 0.45455
) -> None:
    row = bytes([0]) + bytes(rgb) * width
    data = b"\x89PNG\r\n\x1a\n"
    data += _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    if gamma is not None:
        data += _chunk(b"gAMA", struct.pack(">I", round(gamma * 100000)))
    data += _chunk(b"IDAT", zlib.compress(row * height))
    data += _chunk(b"IEND", b"")
    path.write_bytes(data)


def test_image_stats_detects_black_white_and_gamma_mismatch(tmp_path: Path) -> None:
    stats = load_script("image_stats")
    black = tmp_path / "black.png"
    white = tmp_path / "white.png"
    linear = tmp_path / "linear.png"
    _write_png(black, 4, 4, (0, 0, 0))
    _write_png(white, 4, 4, (255, 255, 255))
    _write_png(linear, 4, 4, (128, 128, 128), gamma=1.0)

    black_result = stats.image_stats(image_path=str(black), expected_color_space="srgb")
    white_result = stats.image_stats(image_path=str(white), expected_color_space="srgb")
    gamma_result = stats.image_stats(image_path=str(linear), expected_color_space="srgb")

    assert black_result["context"]["is_black"] is True
    assert white_result["context"]["is_white"] is True
    assert gamma_result["context"]["gamma_status"] == "mismatch"
    assert gamma_result["context"]["gamma_broken"] is True


def test_image_stats_rejects_decoded_data_larger_than_declared_dimensions(
    tmp_path: Path,
) -> None:
    stats = load_script("image_stats")
    oversized = tmp_path / "oversized.png"
    data = b"\x89PNG\r\n\x1a\n"
    data += _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    data += _chunk(b"IDAT", zlib.compress(b"\x00" + b"\x00\x00\x00" * 1000))
    data += _chunk(b"IEND", b"")
    oversized.write_bytes(data)

    result = stats.image_stats(image_path=str(oversized))

    assert result["success"] is False
    assert result["error"] == "invalid-image"


def test_comparison_sheet_packages_images_without_scoring(tmp_path: Path) -> None:
    comparison = load_script("make_comparison_sheet")
    reference = tmp_path / "reference.png"
    front = tmp_path / "front.png"
    output = tmp_path / "comparison.png"
    _write_png(reference, 8, 4, (255, 0, 0))
    _write_png(front, 4, 8, (0, 0, 255))

    result = comparison.make_comparison_sheet(
        reference_path=str(reference),
        capture_paths=[str(front)],
        output_path=str(output),
        labels=["REFERENCE", "FRONT"],
        tile_width=64,
        tile_height=48,
    )

    assert result["success"] is True
    assert result["context"]["tile_count"] == 2
    assert result["context"]["width"] == 128
    assert result["context"]["height"] > 48
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert "score" not in result["context"]

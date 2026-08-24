"""Bounded 8-bit PNG codec and tiny renderer used by the review tools."""

from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path
from typing import Optional

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_PIXELS = 16_777_216
MAX_DIMENSION = 8192


class Image:
    def __init__(
        self,
        width: int,
        height: int,
        pixels: bytes,
        *,
        gamma: Optional[float] = None,
        srgb: bool = False,
    ) -> None:
        self.width = width
        self.height = height
        self.pixels = pixels
        self.gamma = gamma
        self.srgb = srgb


def _paeth(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    if up_distance <= upper_left_distance:
        return up
    return upper_left


def _chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def resolve_input(path_text: str) -> Path:
    if not isinstance(path_text, str) or not path_text.strip():
        raise ValueError("image path must be a non-empty string")
    candidate = Path(path_text).expanduser()
    if candidate.is_symlink():
        raise ValueError(f"symbolic-link image inputs are not accepted: {candidate}")
    path = candidate.resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"image path is not a regular file: {path}")
    if path.suffix.lower() != ".png":
        raise ValueError(f"only 8-bit PNG images are supported: {path.name}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"image exceeds the {MAX_FILE_BYTES} byte limit: {path.name}")
    return path


def resolve_output(path_text: str, *, overwrite: bool, inputs: set[Path]) -> Path:
    if not isinstance(path_text, str) or not path_text.strip():
        raise ValueError("output_path must be a non-empty string")
    candidate = Path(path_text).expanduser()
    if candidate.suffix.lower() != ".png":
        raise ValueError("output_path must end in .png")
    parent = candidate.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError("output parent must be a directory")
    output = parent / candidate.name
    if output in inputs:
        raise ValueError("output_path must not replace an input image")
    if output.is_symlink():
        raise ValueError("symbolic-link outputs are not accepted")
    if output.exists() and not overwrite:
        raise ValueError("output already exists; set overwrite=true to replace it")
    if output.exists() and not output.is_file():
        raise ValueError("output_path is not a regular file")
    return output


def read_png(path: Path) -> Image:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError(f"invalid PNG signature: {path.name}")

    position = len(PNG_SIGNATURE)
    width = height = bit_depth = color_type = interlace = None
    gamma: Optional[float] = None
    srgb = False
    compressed = bytearray()
    saw_end = False
    while position + 12 <= len(data):
        length = struct.unpack_from(">I", data, position)[0]
        position += 4
        if length > MAX_FILE_BYTES or position + 8 + length > len(data):
            raise ValueError(f"invalid PNG chunk length: {path.name}")
        kind = data[position : position + 4]
        position += 4
        payload = data[position : position + length]
        position += length
        expected_crc = struct.unpack_from(">I", data, position)[0]
        position += 4
        actual_crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            raise ValueError(f"PNG chunk checksum mismatch: {path.name}")
        if kind == b"IHDR":
            if length != 13 or width is not None:
                raise ValueError(f"invalid PNG header: {path.name}")
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if compression != 0 or filtering != 0:
                raise ValueError(f"unsupported PNG compression or filter method: {path.name}")
        elif kind == b"IDAT":
            compressed.extend(payload)
            if len(compressed) > MAX_FILE_BYTES:
                raise ValueError(f"compressed PNG data is too large: {path.name}")
        elif kind == b"gAMA" and length == 4:
            gamma_value = struct.unpack(">I", payload)[0]
            if gamma_value == 0:
                raise ValueError(f"PNG gAMA value must be greater than zero: {path.name}")
            gamma = gamma_value / 100000.0
        elif kind == b"sRGB":
            srgb = True
        elif kind == b"IEND":
            saw_end = True
            break

    if not saw_end or width is None or height is None:
        raise ValueError(f"incomplete PNG: {path.name}")
    if width < 1 or height < 1 or width > MAX_DIMENSION or height > MAX_DIMENSION:
        raise ValueError(f"PNG dimensions are outside the supported range: {width}x{height}")
    if width * height > MAX_PIXELS:
        raise ValueError(f"PNG exceeds the {MAX_PIXELS} pixel limit: {path.name}")
    channels_by_type = {0: 1, 2: 3, 4: 2, 6: 4}
    channels = channels_by_type.get(color_type)
    if bit_depth != 8 or channels is None or interlace != 0:
        raise ValueError(
            "only non-interlaced 8-bit grayscale, RGB, gray-alpha, and RGBA PNGs are supported"
        )

    stride = width * channels
    expected_size = height * (stride + 1)
    try:
        decompressor = zlib.decompressobj()
        raw = decompressor.decompress(bytes(compressed), expected_size + 1)
    except zlib.error as exc:
        raise ValueError(f"invalid compressed PNG data: {path.name}") from exc
    if (
        len(raw) > expected_size
        or not decompressor.eof
        or decompressor.unconsumed_tail
        or decompressor.unused_data
    ):
        raise ValueError(f"decoded PNG data exceeds its declared dimensions: {path.name}")
    if len(raw) != expected_size:
        raise ValueError(f"unexpected decoded PNG size: {path.name}")

    previous = bytearray(stride)
    rgb = bytearray(width * height * 3)
    raw_offset = 0
    rgb_offset = 0
    for _row_index in range(height):
        filter_type = raw[raw_offset]
        raw_offset += 1
        row = bytearray(raw[raw_offset : raw_offset + stride])
        raw_offset += stride
        if filter_type not in {0, 1, 2, 3, 4}:
            raise ValueError(f"unsupported PNG row filter: {filter_type}")
        for index in range(stride):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                row[index] = (row[index] + left) & 0xFF
            elif filter_type == 2:
                row[index] = (row[index] + up) & 0xFF
            elif filter_type == 3:
                row[index] = (row[index] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                row[index] = (row[index] + _paeth(left, up, upper_left)) & 0xFF
        previous = row
        for pixel_offset in range(0, stride, channels):
            if color_type == 0:
                red = green = blue = row[pixel_offset]
                alpha = 255
            elif color_type == 2:
                red, green, blue = row[pixel_offset : pixel_offset + 3]
                alpha = 255
            elif color_type == 4:
                red = green = blue = row[pixel_offset]
                alpha = row[pixel_offset + 1]
            else:
                red, green, blue, alpha = row[pixel_offset : pixel_offset + 4]
            if alpha != 255:
                background = (32, 34, 38)
                red = (red * alpha + background[0] * (255 - alpha)) // 255
                green = (green * alpha + background[1] * (255 - alpha)) // 255
                blue = (blue * alpha + background[2] * (255 - alpha)) // 255
            rgb[rgb_offset : rgb_offset + 3] = bytes((red, green, blue))
            rgb_offset += 3
    return Image(width, height, bytes(rgb), gamma=gamma, srgb=srgb)


def encode_png(image: Image) -> bytes:
    if (
        image.width < 1
        or image.height < 1
        or image.width > MAX_DIMENSION
        or image.height > MAX_DIMENSION
        or image.width * image.height > MAX_PIXELS
    ):
        raise ValueError("PNG dimensions exceed the supported limits")
    if len(image.pixels) != image.width * image.height * 3:
        raise ValueError("RGB pixel buffer size does not match image dimensions")
    rows = bytearray()
    stride = image.width * 3
    for row_index in range(image.height):
        rows.append(0)
        start = row_index * stride
        rows.extend(image.pixels[start : start + stride])
    header = struct.pack(">IIBBBBB", image.width, image.height, 8, 2, 0, 0, 0)
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"gAMA", struct.pack(">I", 45455))
        + _chunk(b"sRGB", b"\x00")
        + _chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
        + _chunk(b"IEND", b"")
    )


def write_png_atomic(path: Path, image: Image) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if temporary.exists():
        raise ValueError(f"temporary output already exists: {temporary.name}")
    try:
        with temporary.open("xb") as stream:
            stream.write(encode_png(image))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def new_canvas(width: int, height: int, color: tuple[int, int, int]) -> bytearray:
    if (
        width < 1
        or height < 1
        or width > MAX_DIMENSION
        or height > MAX_DIMENSION
        or width * height > MAX_PIXELS
    ):
        raise ValueError("comparison sheet dimensions exceed the supported limits")
    return bytearray(bytes(color) * (width * height))


def fill_rect(
    pixels: bytearray,
    canvas_width: int,
    canvas_height: int,
    x: int,
    y: int,
    width: int,
    height: int,
    color: tuple[int, int, int],
) -> None:
    left = max(0, x)
    top = max(0, y)
    right = min(canvas_width, x + width)
    bottom = min(canvas_height, y + height)
    row = bytes(color) * max(0, right - left)
    for row_index in range(top, bottom):
        offset = (row_index * canvas_width + left) * 3
        pixels[offset : offset + len(row)] = row


def blit_fit(
    pixels: bytearray,
    canvas_width: int,
    canvas_height: int,
    source: Image,
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    scale = min(width / source.width, height / source.height)
    target_width = max(1, round(source.width * scale))
    target_height = max(1, round(source.height * scale))
    start_x = x + (width - target_width) // 2
    start_y = y + (height - target_height) // 2
    for target_y in range(target_height):
        source_y = min(source.height - 1, target_y * source.height // target_height)
        for target_x in range(target_width):
            source_x = min(source.width - 1, target_x * source.width // target_width)
            source_offset = (source_y * source.width + source_x) * 3
            canvas_x = start_x + target_x
            canvas_y = start_y + target_y
            if 0 <= canvas_x < canvas_width and 0 <= canvas_y < canvas_height:
                target_offset = (canvas_y * canvas_width + canvas_x) * 3
                pixels[target_offset : target_offset + 3] = source.pixels[
                    source_offset : source_offset + 3
                ]


_FONT = {
    "A": (14, 17, 17, 31, 17, 17, 17),
    "B": (30, 17, 17, 30, 17, 17, 30),
    "C": (14, 17, 16, 16, 16, 17, 14),
    "D": (30, 17, 17, 17, 17, 17, 30),
    "E": (31, 16, 16, 30, 16, 16, 31),
    "F": (31, 16, 16, 30, 16, 16, 16),
    "G": (14, 17, 16, 23, 17, 17, 14),
    "H": (17, 17, 17, 31, 17, 17, 17),
    "I": (31, 4, 4, 4, 4, 4, 31),
    "J": (7, 2, 2, 2, 18, 18, 12),
    "K": (17, 18, 20, 24, 20, 18, 17),
    "L": (16, 16, 16, 16, 16, 16, 31),
    "M": (17, 27, 21, 21, 17, 17, 17),
    "N": (17, 25, 21, 19, 17, 17, 17),
    "O": (14, 17, 17, 17, 17, 17, 14),
    "P": (30, 17, 17, 30, 16, 16, 16),
    "Q": (14, 17, 17, 17, 21, 18, 13),
    "R": (30, 17, 17, 30, 20, 18, 17),
    "S": (15, 16, 16, 14, 1, 1, 30),
    "T": (31, 4, 4, 4, 4, 4, 4),
    "U": (17, 17, 17, 17, 17, 17, 14),
    "V": (17, 17, 17, 17, 17, 10, 4),
    "W": (17, 17, 17, 21, 21, 21, 10),
    "X": (17, 17, 10, 4, 10, 17, 17),
    "Y": (17, 17, 10, 4, 4, 4, 4),
    "Z": (31, 1, 2, 4, 8, 16, 31),
    "0": (14, 17, 19, 21, 25, 17, 14),
    "1": (4, 12, 4, 4, 4, 4, 14),
    "2": (14, 17, 1, 2, 4, 8, 31),
    "3": (30, 1, 1, 14, 1, 1, 30),
    "4": (2, 6, 10, 18, 31, 2, 2),
    "5": (31, 16, 16, 30, 1, 1, 30),
    "6": (14, 16, 16, 30, 17, 17, 14),
    "7": (31, 1, 2, 4, 8, 8, 8),
    "8": (14, 17, 17, 14, 17, 17, 14),
    "9": (14, 17, 17, 15, 1, 1, 14),
    "-": (0, 0, 0, 31, 0, 0, 0),
    "_": (0, 0, 0, 0, 0, 0, 31),
    ".": (0, 0, 0, 0, 0, 12, 12),
    ":": (0, 12, 12, 0, 12, 12, 0),
    "/": (1, 2, 2, 4, 8, 8, 16),
    " ": (0, 0, 0, 0, 0, 0, 0),
}


def draw_text(
    pixels: bytearray,
    canvas_width: int,
    canvas_height: int,
    x: int,
    y: int,
    text: str,
    *,
    scale: int = 2,
    color: tuple[int, int, int] = (235, 239, 244),
    max_characters: int = 40,
) -> None:
    cursor = x
    for character in text.upper()[:max_characters]:
        glyph = _FONT.get(character, _FONT["-"])
        for row_index, bits in enumerate(glyph):
            for column in range(5):
                if bits & (1 << (4 - column)):
                    fill_rect(
                        pixels,
                        canvas_width,
                        canvas_height,
                        cursor + column * scale,
                        y + row_index * scale,
                        scale,
                        scale,
                        color,
                    )
        cursor += 6 * scale

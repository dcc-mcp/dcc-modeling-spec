"""Compute bounded PNG statistics and detect unusable review frames."""

from __future__ import annotations

from _image import read_png, resolve_input
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


def _gamma_status(gamma: float | None, srgb: bool, expected_color_space: str) -> str:
    if expected_color_space == "auto":
        return "not_requested"
    if expected_color_space == "srgb":
        if srgb and (gamma is None or abs(gamma - 0.45455) <= 0.02):
            return "valid"
        if gamma is not None and abs(gamma - 0.45455) <= 0.02:
            return "valid"
        return "mismatch" if gamma is not None or srgb else "missing"
    if expected_color_space == "linear":
        if not srgb and gamma is not None and abs(gamma - 1.0) <= 0.02:
            return "valid"
        return "mismatch" if gamma is not None or srgb else "missing"
    return "invalid_expectation"


@skill_entry
def image_stats(
    image_path: str,
    expected_color_space: str = "auto",
    black_threshold: float = 0.01,
    white_threshold: float = 0.99,
    uniform_fraction: float = 0.99,
    **kwargs,
) -> dict:
    """Analyze an 8-bit PNG without judging modeling quality."""
    if expected_color_space not in {"auto", "srgb", "linear"}:
        return skill_error(
            "Invalid expected color space",
            "invalid-color-space",
            possible_solutions=["Use auto, srgb, or linear."],
        )
    if not 0 <= black_threshold < white_threshold <= 1 or not 0.5 <= uniform_fraction <= 1:
        return skill_error(
            "Invalid image-stat thresholds",
            "invalid-thresholds",
            possible_solutions=[
                "Use ordered black/white thresholds from 0 to 1 and "
                "uniform_fraction between 0.5 and 1."
            ],
        )
    try:
        path = resolve_input(image_path)
        image = read_png(path)
    except (OSError, ValueError) as exc:
        return skill_error(
            "Could not inspect the image",
            "invalid-image",
            possible_solutions=[
                "Provide a regular, non-interlaced 8-bit PNG within the documented limits."
            ],
            reason=str(exc),
        )

    pixel_count = image.width * image.height
    channel_sums = [0, 0, 0]
    minimum = [255, 255, 255]
    maximum = [0, 0, 0]
    luma_sum = 0.0
    black_pixels = 0
    white_pixels = 0
    for offset in range(0, len(image.pixels), 3):
        red, green, blue = image.pixels[offset : offset + 3]
        for channel, value in enumerate((red, green, blue)):
            channel_sums[channel] += value
            minimum[channel] = min(minimum[channel], value)
            maximum[channel] = max(maximum[channel], value)
        luma = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255.0
        luma_sum += luma
        if luma <= black_threshold:
            black_pixels += 1
        if luma >= white_threshold:
            white_pixels += 1

    black_fraction = black_pixels / pixel_count
    white_fraction = white_pixels / pixel_count
    gamma_status = _gamma_status(image.gamma, image.srgb, expected_color_space)
    return skill_success(
        "Image statistics ready",
        image_path=str(path),
        width=image.width,
        height=image.height,
        pixel_count=pixel_count,
        channel_mean=[round(value / pixel_count / 255.0, 6) for value in channel_sums],
        channel_min=[round(value / 255.0, 6) for value in minimum],
        channel_max=[round(value / 255.0, 6) for value in maximum],
        mean_luma=round(luma_sum / pixel_count, 6),
        black_fraction=round(black_fraction, 6),
        white_fraction=round(white_fraction, 6),
        is_black=black_fraction >= uniform_fraction,
        is_white=white_fraction >= uniform_fraction,
        expected_color_space=expected_color_space,
        png_gamma=image.gamma,
        png_srgb=image.srgb,
        gamma_status=gamma_status,
        gamma_broken=gamma_status == "mismatch",
    )

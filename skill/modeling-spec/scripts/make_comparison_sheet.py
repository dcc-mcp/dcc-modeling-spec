"""Package one reference and bounded multi-view PNG captures into one sheet."""

from __future__ import annotations

from _image import (
    Image,
    blit_fit,
    draw_text,
    fill_rect,
    new_canvas,
    read_png,
    resolve_input,
    resolve_output,
    write_png_atomic,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


@skill_entry
def make_comparison_sheet(
    reference_path: str,
    capture_paths: list[str],
    output_path: str,
    labels: list[str] | None = None,
    tile_width: int = 640,
    tile_height: int = 360,
    overwrite: bool = False,
    **kwargs,
) -> dict:
    """Create a deterministic review artifact; this tool never assigns a score."""
    if not isinstance(capture_paths, list) or not 1 <= len(capture_paths) <= 8:
        return skill_error(
            "capture_paths must contain between one and eight images",
            "invalid-captures",
            possible_solutions=["Pass the bounded views for one review cycle."],
        )
    if (
        not isinstance(tile_width, int)
        or isinstance(tile_width, bool)
        or not 64 <= tile_width <= 2048
    ):
        return skill_error(
            "Invalid tile width",
            "invalid-dimensions",
            possible_solutions=["Use tile_width from 64 to 2048 pixels."],
        )
    if (
        not isinstance(tile_height, int)
        or isinstance(tile_height, bool)
        or not 32 <= tile_height <= 2048
    ):
        return skill_error(
            "Invalid tile height",
            "invalid-dimensions",
            possible_solutions=["Use tile_height from 32 to 2048 pixels."],
        )

    path_values = [reference_path, *capture_paths]
    if labels is None:
        normalized_labels = [
            "REFERENCE",
            *[f"VIEW {index}" for index in range(1, len(path_values))],
        ]
    elif (
        not isinstance(labels, list)
        or len(labels) != len(path_values)
        or not all(isinstance(label, str) and label.strip() for label in labels)
    ):
        return skill_error(
            "labels must contain one non-empty label per tile",
            "invalid-labels",
            possible_solutions=["Pass reference plus capture labels in tile order."],
        )
    else:
        normalized_labels = [label.strip() for label in labels]

    try:
        input_paths = [resolve_input(value) for value in path_values]
        if len(set(input_paths)) != len(input_paths):
            raise ValueError("each comparison tile must use a distinct input path")
        images = [read_png(path) for path in input_paths]
        output = resolve_output(output_path, overwrite=bool(overwrite), inputs=set(input_paths))
        header_height = 32
        width = tile_width * len(images)
        height = tile_height + header_height
        pixels = new_canvas(width, height, (24, 26, 30))
        for index, (image, label) in enumerate(zip(images, normalized_labels)):
            tile_x = index * tile_width
            fill_rect(pixels, width, height, tile_x, 0, tile_width, header_height, (38, 42, 48))
            if index:
                fill_rect(pixels, width, height, tile_x, 0, 1, height, (92, 99, 110))
            draw_text(pixels, width, height, tile_x + 10, 9, label)
            blit_fit(pixels, width, height, image, tile_x, header_height, tile_width, tile_height)
        write_png_atomic(output, Image(width, height, bytes(pixels), gamma=0.45455, srgb=True))
    except (OSError, ValueError) as exc:
        return skill_error(
            "Could not create the comparison sheet",
            "comparison-sheet-failed",
            possible_solutions=[
                "Use distinct regular 8-bit PNG inputs and a writable .png output path."
            ],
            reason=str(exc),
        )

    return skill_success(
        "Comparison sheet packaged without scoring",
        output_path=str(output),
        width=width,
        height=height,
        tile_count=len(images),
        labels=normalized_labels,
        packaged_only=True,
    )

"""Return a deterministic Modeling Spec v2 template."""

from __future__ import annotations

from dcc_mcp_core.skill import skill_entry, skill_success

_UNITS = frozenset({"mm", "cm", "m", "in", "ft"})


@skill_entry
def get_spec_template(
    asset_name: str = "Untitled asset",
    linear_unit: str = "cm",
    **kwargs,
) -> dict:
    """Return a fresh spec template; no host state is read or changed."""
    name = asset_name.strip() if isinstance(asset_name, str) else ""
    unit = linear_unit.strip().lower() if isinstance(linear_unit, str) else ""
    if not name:
        name = "Untitled asset"
    if unit not in _UNITS:
        unit = "cm"

    spec = {
        "spec_version": "2.0",
        "asset": {
            "name": name,
            "linear_unit": unit,
            "purpose": "",
            "reference_ids": [],
        },
        "parts": [],
        "never": [],
        "proportions": [],
        "hierarchy": {"root": "asset_root", "nodes": []},
        "materials": [],
        "quality_priority": [],
        "uncertainties": [],
        "acceptance": {
            "stages": [
                {
                    "id": "blockout",
                    "checks": ["all_required_parts", "hierarchy", "proportions"],
                },
                {
                    "id": "final",
                    "checks": [
                        "all_required_parts",
                        "hierarchy",
                        "proportions",
                        "uv_coverage",
                        "material_bindings",
                        "topology",
                    ],
                },
            ],
            "max_corrections_per_stage": 3,
            "max_total_corrections": 8,
        },
    }
    return skill_success(
        "Modeling Spec v2 template ready",
        spec=spec,
        next_action="Fill all sections, then call validate_spec with strict_quality=true.",
    )

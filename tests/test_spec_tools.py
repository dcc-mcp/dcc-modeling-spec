from __future__ import annotations

from conftest import load_script


def _valid_spec() -> dict:
    template = load_script("get_spec_template").get_spec_template(
        asset_name="Scout Rotorcraft",
        linear_unit="cm",
    )
    spec = template["context"]["spec"]
    spec["parts"] = [
        {
            "id": "body",
            "label": "Body",
            "required": True,
            "parent": "asset_root",
            "pivot": "center_of_mass",
            "expected_euler_characteristic": 2,
        },
        {
            "id": "rotor",
            "label": "Main rotor",
            "required": True,
            "parent": "body",
            "pivot": "rotor_axis",
            "expected_euler_characteristic": 2,
        },
    ]
    spec["never"] = ["Do not merge the rotor into the body mesh"]
    spec["proportions"] = [
        {
            "id": "rotor_to_body",
            "numerator": "rotor.diameter",
            "denominator": "body.length",
            "target": 1.2,
            "tolerance": 0.05,
        }
    ]
    spec["hierarchy"] = {
        "root": "asset_root",
        "nodes": [
            {"id": "body", "parent": "asset_root", "pivot": "center_of_mass"},
            {"id": "rotor", "parent": "body", "pivot": "rotor_axis"},
        ],
    }
    spec["materials"] = [
        {
            "id": "paint",
            "slots": ["body"],
            "required_channels": ["base_color", "roughness", "normal"],
        },
        {
            "id": "metal",
            "slots": ["rotor"],
            "required_channels": ["base_color", "metallic", "roughness"],
        },
    ]
    spec["quality_priority"] = ["silhouette", "proportions", "materials", "micro_detail"]
    spec["uncertainties"] = [
        {"question": "Exact tail profile", "resolution": "request_reference", "blocking": False}
    ]
    spec["acceptance"] = {
        "stages": [
            {"id": "blockout", "checks": ["all_required_parts", "proportions"]},
            {"id": "final", "checks": ["uv_coverage", "material_bindings", "topology"]},
        ],
        "max_corrections_per_stage": 3,
        "max_total_corrections": 8,
    }
    return spec


def test_template_and_strict_spec_gate() -> None:
    validate = load_script("validate_spec")
    spec = _valid_spec()

    result = validate.validate_spec(spec=spec, strict_quality=True)

    assert result["success"] is True
    assert result["context"]["passed"] is True
    assert result["context"]["failures"] == []


def test_shallow_spec_is_blocked_with_actionable_failures() -> None:
    template = load_script("get_spec_template").get_spec_template(asset_name="Shallow")
    validate = load_script("validate_spec")

    result = validate.validate_spec(spec=template["context"]["spec"], strict_quality=True)

    assert result["success"] is True
    assert result["context"]["passed"] is False
    codes = {failure["code"] for failure in result["context"]["failures"]}
    assert {"parts_missing", "never_missing", "proportions_missing", "materials_missing"}.issubset(
        codes
    )
    assert all(failure["remediation"] for failure in result["context"]["failures"])


def test_non_finite_proportion_and_incoherent_caps_are_rejected() -> None:
    validate = load_script("validate_spec")
    spec = _valid_spec()
    spec["proportions"][0]["target"] = float("nan")
    spec["acceptance"]["max_corrections_per_stage"] = 5
    spec["acceptance"]["max_total_corrections"] = 4

    result = validate.validate_spec(spec=spec, strict_quality=True)

    codes = {failure["code"] for failure in result["context"]["failures"]}
    assert "proportion_target_invalid" in codes
    assert "correction_caps_incoherent" in codes


def test_spec_requires_owned_topology_expectations() -> None:
    validate = load_script("validate_spec")
    spec = _valid_spec()
    del spec["parts"][1]["expected_euler_characteristic"]

    result = validate.validate_spec(spec=spec, strict_quality=True)

    failures = result["context"]["failures"]
    assert result["context"]["passed"] is False
    assert any(
        item["code"] == "part_topology_expectation_missing"
        and item["path"] == "parts[1].expected_euler_characteristic"
        for item in failures
    )


def test_scene_validator_catches_real_uv_and_material_defects() -> None:
    validate = load_script("validate_scene_vs_spec")
    spec = _valid_spec()
    scene = {
        "parts": [
            {
                "id": "body",
                "parent": "asset_root",
                "pivot": "center_of_mass",
                "material_slots": ["paint"],
            },
            {"id": "rotor", "parent": "body", "pivot": "rotor_axis", "material_slots": [None]},
        ],
        "meshes": [
            {
                "part_id": "body",
                "uv_coverage": 0.69,
                "unbound_material_slots": 0,
                "non_manifold_edges": 0,
                "euler_characteristic": 2,
            },
            {
                "part_id": "rotor",
                "uv_coverage": 1.0,
                "unbound_material_slots": 1,
                "non_manifold_edges": 0,
                "euler_characteristic": 2,
            },
        ],
        "proportions": {"rotor_to_body": 1.2},
    }

    result = validate.validate_scene_vs_spec(spec=spec, scene=scene, stage="final")

    assert result["success"] is True
    assert result["context"]["passed"] is False
    failures = result["context"]["failures"]
    assert any(
        item["code"] == "uv_coverage_incomplete" and item["path"] == "meshes.body"
        for item in failures
    )
    assert any(
        item["code"] == "material_slot_unbound" and item["path"] == "meshes.rotor"
        for item in failures
    )


def test_scene_validator_passes_complete_measured_facts() -> None:
    validate = load_script("validate_scene_vs_spec")
    spec = _valid_spec()
    scene = {
        "parts": [
            {
                "id": "body",
                "parent": "asset_root",
                "pivot": "center_of_mass",
                "material_slots": ["paint"],
            },
            {"id": "rotor", "parent": "body", "pivot": "rotor_axis", "material_slots": ["metal"]},
        ],
        "meshes": [
            {
                "part_id": part,
                "uv_coverage": 1.0,
                "unbound_material_slots": 0,
                "non_manifold_edges": 0,
                "euler_characteristic": 2,
            }
            for part in ("body", "rotor")
        ],
        "proportions": {"rotor_to_body": 1.2},
    }

    result = validate.validate_scene_vs_spec(spec=spec, scene=scene, stage="final")

    assert result["context"]["passed"] is True
    assert result["context"]["failures"] == []


def test_scene_cannot_self_author_expected_topology() -> None:
    validate = load_script("validate_scene_vs_spec")
    spec = _valid_spec()
    scene = {
        "parts": [
            {
                "id": "body",
                "parent": "asset_root",
                "pivot": "center_of_mass",
                "material_slots": ["paint"],
            },
            {
                "id": "rotor",
                "parent": "body",
                "pivot": "rotor_axis",
                "material_slots": ["metal"],
            },
        ],
        "meshes": [
            {
                "part_id": part,
                "uv_coverage": 1.0,
                "unbound_material_slots": 0,
                "non_manifold_edges": 0,
                "euler_characteristic": 999,
                "expected_euler_characteristic": 999,
            }
            for part in ("body", "rotor")
        ],
        "proportions": {"rotor_to_body": 1.2},
    }

    result = validate.validate_scene_vs_spec(spec=spec, scene=scene, stage="final")

    failures = result["context"]["failures"]
    assert result["context"]["passed"] is False
    mismatches = [item for item in failures if item["code"] == "euler_characteristic_mismatch"]
    assert len(mismatches) == 2
    assert all(item["expected"] == 2 for item in mismatches)
    assert sum(item["code"] == "measurement_field_forbidden" for item in failures) == 2

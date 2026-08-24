"""Compare host-measured scene facts with a validated Modeling Spec v2."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from _common import failure, is_nonempty_string, is_number
from dcc_mcp_core.skill import skill_entry, skill_success


def _stage_checks(spec: Mapping[str, Any], stage: str) -> tuple[set[str], list[dict[str, Any]]]:
    acceptance = spec.get("acceptance")
    if not isinstance(acceptance, Mapping) or not isinstance(acceptance.get("stages"), list):
        return set(), [
            failure(
                "acceptance_missing",
                "spec.acceptance",
                "spec has no staged acceptance protocol",
                "Validate the spec before measuring the scene.",
            )
        ]
    for item in acceptance["stages"]:
        if isinstance(item, Mapping) and item.get("id") == stage:
            checks = item.get("checks")
            if (
                isinstance(checks, list)
                and checks
                and all(isinstance(check, str) for check in checks)
            ):
                return set(checks), []
            break
    return set(), [
        failure(
            "stage_unknown",
            "stage",
            f"stage is not declared by the spec: {stage}",
            "Choose one of the spec acceptance stage ids.",
            stage=stage,
        )
    ]


def _records_by_id(
    records: Any, path: str, failures: list[dict[str, Any]]
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(records, list):
        failures.append(
            failure(
                "measurement_missing",
                path,
                f"{path} measurements must be an array",
                f"Measure {path} with the owning adapter and retry.",
            )
        )
        return {}
    result: dict[str, Mapping[str, Any]] = {}
    for index, record in enumerate(records):
        record_path = f"{path}[{index}]"
        if not isinstance(record, Mapping):
            failures.append(
                failure(
                    "measurement_invalid",
                    record_path,
                    "measurement must be an object",
                    "Export structured measured facts from the adapter.",
                )
            )
            continue
        identifier = record.get("id") if path == "parts" else record.get("part_id")
        if not is_nonempty_string(identifier):
            failures.append(
                failure(
                    "measurement_id_missing",
                    record_path,
                    "measurement has no stable part id",
                    "Map the measured object to a declared spec part id.",
                )
            )
            continue
        if identifier in result:
            failures.append(
                failure(
                    "measurement_id_duplicate",
                    record_path,
                    f"duplicate measurement for part: {identifier}",
                    "Return exactly one measurement record per part.",
                )
            )
            continue
        result[identifier] = record
    return result


def _check_parts(
    spec_parts: list[Any],
    measured: dict[str, Mapping[str, Any]],
    checks: set[str],
    failures: list[dict[str, Any]],
) -> set[str]:
    required: set[str] = set()
    for item in spec_parts:
        if not isinstance(item, Mapping) or not is_nonempty_string(item.get("id")):
            continue
        part_id = item["id"]
        if item.get("required") is True:
            required.add(part_id)
        actual = measured.get(part_id)
        if actual is None:
            continue
        if "hierarchy" in checks:
            for field in ("parent", "pivot"):
                expected = item.get(field)
                if expected != actual.get(field):
                    failures.append(
                        failure(
                            f"{field}_mismatch",
                            f"parts.{part_id}.{field}",
                            f"{field} differs from the spec",
                            f"Set {part_id}.{field} to {expected!r}, then remeasure.",
                            expected=expected,
                            actual=actual.get(field),
                        )
                    )
    if "all_required_parts" in checks:
        missing = sorted(required - measured.keys())
        for part_id in missing:
            failures.append(
                failure(
                    "required_part_missing",
                    f"parts.{part_id}",
                    f"required part is missing: {part_id}",
                    "Create or restore the declared part, then rerun the stage gate.",
                    part_id=part_id,
                )
            )
    return required


def _check_materials(
    spec: Mapping[str, Any],
    parts: dict[str, Mapping[str, Any]],
    meshes: dict[str, Mapping[str, Any]],
    failures: list[dict[str, Any]],
) -> None:
    expected_by_part: dict[str, set[str]] = {}
    materials = spec.get("materials")
    if isinstance(materials, list):
        for material in materials:
            if not isinstance(material, Mapping) or not is_nonempty_string(material.get("id")):
                continue
            slots = material.get("slots")
            if isinstance(slots, list):
                for part_id in slots:
                    if is_nonempty_string(part_id):
                        expected_by_part.setdefault(part_id, set()).add(material["id"])

    for part_id, expected in expected_by_part.items():
        part = parts.get(part_id)
        if part is None:
            continue
        slots = part.get("material_slots")
        actual = (
            {slot for slot in slots if is_nonempty_string(slot)}
            if isinstance(slots, list)
            else set()
        )
        missing = sorted(expected - actual)
        if missing:
            failures.append(
                failure(
                    "material_binding_missing",
                    f"parts.{part_id}.material_slots",
                    f"missing material bindings: {', '.join(missing)}",
                    "Bind the declared materials to the part and verify the assignment.",
                    materials=missing,
                )
            )

    for part_id, mesh in meshes.items():
        unbound = mesh.get("unbound_material_slots")
        if not isinstance(unbound, int) or isinstance(unbound, bool) or unbound < 0:
            failures.append(
                failure(
                    "measurement_missing",
                    f"meshes.{part_id}.unbound_material_slots",
                    "unbound material slot count is missing",
                    "Measure material slot bindings in the owning adapter.",
                )
            )
        elif unbound:
            failures.append(
                failure(
                    "material_slot_unbound",
                    f"meshes.{part_id}",
                    f"mesh has {unbound} unbound material slot(s)",
                    "Bind or remove every unbound slot, then remeasure.",
                    actual=unbound,
                    expected=0,
                )
            )


def _check_meshes(
    required_parts: set[str],
    meshes: dict[str, Mapping[str, Any]],
    checks: set[str],
    failures: list[dict[str, Any]],
) -> None:
    for part_id in sorted(required_parts):
        if part_id not in meshes:
            failures.append(
                failure(
                    "mesh_measurement_missing",
                    f"meshes.{part_id}",
                    f"no mesh facts were reported for required part: {part_id}",
                    "Measure UV, material, and topology facts for this part.",
                )
            )

    for part_id, mesh in meshes.items():
        path = f"meshes.{part_id}"
        if "uv_coverage" in checks:
            coverage = mesh.get("uv_coverage")
            if not is_number(coverage) or not 0 <= coverage <= 1:
                failures.append(
                    failure(
                        "measurement_missing",
                        f"{path}.uv_coverage",
                        "UV coverage must be a measured fraction from 0 to 1",
                        "Measure per-mesh UV coverage in the owning adapter.",
                    )
                )
            elif coverage < 1.0:
                failures.append(
                    failure(
                        "uv_coverage_incomplete",
                        path,
                        f"UV coverage is {coverage:.1%}; expected 100%",
                        "Unwrap the missing faces or explicitly revise the spec stage.",
                        actual=coverage,
                        expected=1.0,
                    )
                )
        if "topology" in checks:
            non_manifold = mesh.get("non_manifold_edges")
            if (
                not isinstance(non_manifold, int)
                or isinstance(non_manifold, bool)
                or non_manifold < 0
            ):
                failures.append(
                    failure(
                        "measurement_missing",
                        f"{path}.non_manifold_edges",
                        "non-manifold edge count is missing",
                        "Measure non-manifold topology in the owning adapter.",
                    )
                )
            elif non_manifold:
                failures.append(
                    failure(
                        "non_manifold_topology",
                        path,
                        f"mesh has {non_manifold} non-manifold edge(s)",
                        "Repair the reported edges and remeasure.",
                        actual=non_manifold,
                        expected=0,
                    )
                )
            actual_euler = mesh.get("euler_characteristic")
            expected_euler = mesh.get("expected_euler_characteristic")
            if (
                not isinstance(actual_euler, int)
                or isinstance(actual_euler, bool)
                or not isinstance(expected_euler, int)
                or isinstance(expected_euler, bool)
            ):
                failures.append(
                    failure(
                        "measurement_missing",
                        f"{path}.euler_characteristic",
                        "actual and expected Euler characteristics are required",
                        "Measure V-E+F and declare the expected topology value.",
                    )
                )
            elif actual_euler != expected_euler:
                failures.append(
                    failure(
                        "euler_characteristic_mismatch",
                        path,
                        f"Euler characteristic is {actual_euler}; expected {expected_euler}",
                        "Inspect holes, shells, and topology changes before continuing.",
                        actual=actual_euler,
                        expected=expected_euler,
                    )
                )


def _check_proportions(
    spec: Mapping[str, Any],
    scene: Mapping[str, Any],
    failures: list[dict[str, Any]],
) -> None:
    measured = scene.get("proportions")
    if not isinstance(measured, Mapping):
        failures.append(
            failure(
                "measurement_missing",
                "proportions",
                "measured proportions are missing",
                "Measure every declared proportion in the owning adapter.",
            )
        )
        return
    declared = spec.get("proportions")
    if not isinstance(declared, list):
        return
    for item in declared:
        if not isinstance(item, Mapping) or not is_nonempty_string(item.get("id")):
            continue
        identifier = item["id"]
        value = measured.get(identifier)
        target = item.get("target")
        tolerance = item.get("tolerance")
        if not is_number(value):
            failures.append(
                failure(
                    "proportion_measurement_missing",
                    f"proportions.{identifier}",
                    f"proportion is not measured: {identifier}",
                    "Measure the declared numerator/denominator ratio.",
                )
            )
        elif is_number(target) and is_number(tolerance) and abs(value - target) > tolerance:
            failures.append(
                failure(
                    "proportion_out_of_tolerance",
                    f"proportions.{identifier}",
                    f"measured ratio {value} is outside {target} ± {tolerance}",
                    "Adjust the declared dimensions or refine the spec with explicit approval.",
                    actual=value,
                    expected=target,
                    tolerance=tolerance,
                )
            )


@skill_entry
def validate_scene_vs_spec(spec: dict, scene: dict, stage: str = "final", **kwargs) -> dict:
    """Validate measured facts only; this function never executes host code."""
    failures: list[dict[str, Any]] = []
    if not isinstance(spec, Mapping) or not isinstance(scene, Mapping):
        failures.append(
            failure(
                "payload_invalid",
                "spec|scene",
                "spec and scene must both be objects",
                "Pass a validated spec and host-measured scene facts.",
            )
        )
        return skill_success(
            "Scene validation failed", passed=False, failures=failures, stage=stage
        )
    if spec.get("spec_version") != "2.0":
        failures.append(
            failure(
                "spec_version_invalid",
                "spec.spec_version",
                "scene validation requires a Modeling Spec v2",
                "Validate a v2 spec before measuring the scene.",
            )
        )
    checks, stage_failures = _stage_checks(spec, stage)
    failures.extend(stage_failures)
    spec_parts = spec.get("parts") if isinstance(spec.get("parts"), list) else []
    parts = _records_by_id(scene.get("parts"), "parts", failures)
    meshes = _records_by_id(scene.get("meshes"), "meshes", failures)
    required = _check_parts(spec_parts, parts, checks, failures)
    if "proportions" in checks:
        _check_proportions(spec, scene, failures)
    if "uv_coverage" in checks or "topology" in checks:
        _check_meshes(required, meshes, checks, failures)
    if "material_bindings" in checks:
        _check_materials(spec, parts, meshes, failures)
    passed = not failures
    return skill_success(
        f"Scene passed the {stage} gate"
        if passed
        else f"Scene failed {len(failures)} {stage} check(s)",
        passed=passed,
        failures=failures,
        stage=stage,
        checks=sorted(checks),
        measured_parts=len(parts),
        measured_meshes=len(meshes),
    )

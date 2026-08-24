"""Validate a host-neutral Modeling Spec v2 before scene work begins."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from _common import failure, is_nonempty_string, is_number
from dcc_mcp_core.skill import skill_entry, skill_success

_KNOWN_CHECKS = frozenset(
    {
        "all_required_parts",
        "hierarchy",
        "proportions",
        "uv_coverage",
        "material_bindings",
        "topology",
    }
)


def _require_list(
    spec: Mapping[str, Any],
    field: str,
    failures: list[dict[str, Any]],
    *,
    nonempty: bool,
) -> list[Any]:
    value = spec.get(field)
    if not isinstance(value, list) or (nonempty and not value):
        failures.append(
            failure(
                f"{field}_missing",
                field,
                f"{field} must be {'a non-empty' if nonempty else 'an'} array",
                f"Add the declared {field.replace('_', ' ')} to the spec before building.",
            )
        )
        return []
    return value


def _validate_parts(parts: list[Any], failures: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for index, part in enumerate(parts):
        path = f"parts[{index}]"
        if not isinstance(part, Mapping):
            failures.append(
                failure(
                    "part_invalid",
                    path,
                    "part must be an object",
                    "Replace it with a typed part record.",
                )
            )
            continue
        part_id = part.get("id")
        if not is_nonempty_string(part_id):
            failures.append(
                failure(
                    "part_id_missing",
                    f"{path}.id",
                    "part id is required",
                    "Assign a stable, host-neutral part id.",
                )
            )
            continue
        if part_id in ids:
            failures.append(
                failure(
                    "part_id_duplicate",
                    f"{path}.id",
                    f"duplicate part id: {part_id}",
                    "Keep each part id unique.",
                )
            )
        ids.add(part_id)
        for field in ("label", "parent", "pivot"):
            if not is_nonempty_string(part.get(field)):
                failures.append(
                    failure(
                        f"part_{field}_missing",
                        f"{path}.{field}",
                        f"part {field} is required",
                        f"Declare the part {field}.",
                    )
                )
        if not isinstance(part.get("required"), bool):
            failures.append(
                failure(
                    "part_required_invalid",
                    f"{path}.required",
                    "required must be boolean",
                    "Set required to true or false.",
                )
            )
    return ids


def _validate_proportions(items: list[Any], failures: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for index, item in enumerate(items):
        path = f"proportions[{index}]"
        if not isinstance(item, Mapping):
            failures.append(
                failure(
                    "proportion_invalid",
                    path,
                    "proportion must be an object",
                    "Declare numerator, denominator, target, and tolerance.",
                )
            )
            continue
        identifier = item.get("id")
        if not is_nonempty_string(identifier) or identifier in seen:
            failures.append(
                failure(
                    "proportion_id_invalid",
                    f"{path}.id",
                    "proportion id must be non-empty and unique",
                    "Assign a unique proportion id.",
                )
            )
        else:
            seen.add(identifier)
        for field in ("numerator", "denominator"):
            if not is_nonempty_string(item.get(field)):
                failures.append(
                    failure(
                        f"proportion_{field}_missing",
                        f"{path}.{field}",
                        f"{field} measurement is required",
                        f"Name the measured {field}.",
                    )
                )
        target = item.get("target")
        tolerance = item.get("tolerance")
        if not is_number(target) or target <= 0:
            failures.append(
                failure(
                    "proportion_target_invalid",
                    f"{path}.target",
                    "target must be greater than zero",
                    "Record the intended numeric ratio.",
                )
            )
        if not is_number(tolerance) or tolerance < 0:
            failures.append(
                failure(
                    "proportion_tolerance_invalid",
                    f"{path}.tolerance",
                    "tolerance must be zero or greater",
                    "Record an explicit numeric tolerance.",
                )
            )


def _validate_hierarchy(
    value: Any,
    parts: list[Any],
    part_ids: set[str],
    failures: list[dict[str, Any]],
) -> None:
    if not isinstance(value, Mapping) or not is_nonempty_string(value.get("root")):
        failures.append(
            failure(
                "hierarchy_missing",
                "hierarchy",
                "hierarchy root and nodes are required",
                "Declare a root plus parent and pivot ownership for every part.",
            )
        )
        return
    nodes = value.get("nodes")
    if not isinstance(nodes, list):
        failures.append(
            failure(
                "hierarchy_nodes_missing",
                "hierarchy.nodes",
                "hierarchy nodes must be an array",
                "Add one hierarchy node per part.",
            )
        )
        return
    root = value["root"]
    expected = {
        part["id"]: (part.get("parent"), part.get("pivot"))
        for part in parts
        if isinstance(part, Mapping) and is_nonempty_string(part.get("id"))
    }
    node_ids: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, Mapping):
            failures.append(
                failure(
                    "hierarchy_node_invalid",
                    f"hierarchy.nodes[{index}]",
                    "hierarchy node must be an object",
                    "Declare id, parent, and pivot.",
                )
            )
            continue
        node_id = node.get("id")
        if is_nonempty_string(node_id):
            if node_id in node_ids:
                failures.append(
                    failure(
                        "hierarchy_node_duplicate",
                        f"hierarchy.nodes[{index}].id",
                        f"duplicate hierarchy node: {node_id}",
                        "Keep exactly one hierarchy record per part.",
                    )
                )
            node_ids.add(node_id)
        for field in ("id", "parent", "pivot"):
            if not is_nonempty_string(node.get(field)):
                failures.append(
                    failure(
                        f"hierarchy_{field}_missing",
                        f"hierarchy.nodes[{index}].{field}",
                        f"hierarchy {field} is required",
                        f"Declare the node {field}.",
                    )
                )
        if is_nonempty_string(node_id):
            parent = node.get("parent")
            pivot = node.get("pivot")
            if is_nonempty_string(parent) and parent not in part_ids and parent != root:
                failures.append(
                    failure(
                        "hierarchy_parent_unknown",
                        f"hierarchy.nodes[{index}].parent",
                        f"unknown hierarchy parent: {parent}",
                        "Use the declared root or another declared part id.",
                    )
                )
            expected_values = expected.get(node_id)
            if expected_values is not None and (parent, pivot) != expected_values:
                failures.append(
                    failure(
                        "hierarchy_contract_mismatch",
                        f"hierarchy.nodes[{index}]",
                        "hierarchy node differs from the part parent or pivot contract",
                        "Make the part and hierarchy records agree before building.",
                    )
                )
    missing = sorted(part_ids - node_ids)
    if missing:
        failures.append(
            failure(
                "hierarchy_parts_missing",
                "hierarchy.nodes",
                f"hierarchy omits parts: {', '.join(missing)}",
                "Add a hierarchy node for every declared part.",
                parts=missing,
            )
        )


def _validate_materials(
    items: list[Any], part_ids: set[str], failures: list[dict[str, Any]]
) -> None:
    ids: set[str] = set()
    assigned: set[str] = set()
    for index, item in enumerate(items):
        path = f"materials[{index}]"
        if not isinstance(item, Mapping):
            failures.append(
                failure(
                    "material_invalid",
                    path,
                    "material must be an object",
                    "Declare id, slots, and required channels.",
                )
            )
            continue
        material_id = item.get("id")
        if not is_nonempty_string(material_id) or material_id in ids:
            failures.append(
                failure(
                    "material_id_invalid",
                    f"{path}.id",
                    "material id must be non-empty and unique",
                    "Assign a unique material id.",
                )
            )
        else:
            ids.add(material_id)
        slots = item.get("slots")
        if (
            not isinstance(slots, list)
            or not slots
            or not all(is_nonempty_string(slot) for slot in slots)
        ):
            failures.append(
                failure(
                    "material_slots_missing",
                    f"{path}.slots",
                    "material slots must name one or more parts",
                    "Bind the material contract to declared part ids.",
                )
            )
        else:
            assigned.update(slots)
            unknown = sorted(set(slots) - part_ids)
            if unknown:
                failures.append(
                    failure(
                        "material_slots_unknown",
                        f"{path}.slots",
                        f"material slots reference unknown parts: {', '.join(unknown)}",
                        "Use declared part ids only.",
                        parts=unknown,
                    )
                )
        channels = item.get("required_channels")
        if (
            not isinstance(channels, list)
            or not channels
            or not all(is_nonempty_string(channel) for channel in channels)
        ):
            failures.append(
                failure(
                    "material_channels_missing",
                    f"{path}.required_channels",
                    "required channels must be a non-empty array",
                    "Declare the maps or scalar channels that must exist.",
                )
            )
    unassigned = sorted(part_ids - assigned)
    if unassigned:
        failures.append(
            failure(
                "parts_without_material_contract",
                "materials",
                f"parts lack a material contract: {', '.join(unassigned)}",
                "Assign every declared part to at least one material slot.",
                parts=unassigned,
            )
        )


def _validate_acceptance(value: Any, failures: list[dict[str, Any]]) -> None:
    if not isinstance(value, Mapping):
        failures.append(
            failure(
                "acceptance_missing",
                "acceptance",
                "acceptance protocol is required",
                "Declare staged checks and bounded correction caps.",
            )
        )
        return
    stages = value.get("stages")
    if not isinstance(stages, list) or len(stages) < 2:
        failures.append(
            failure(
                "acceptance_stages_missing",
                "acceptance.stages",
                "at least two acceptance stages are required",
                "Declare a blockout gate and a final gate.",
            )
        )
    else:
        stage_ids: set[str] = set()
        for index, stage in enumerate(stages):
            path = f"acceptance.stages[{index}]"
            if not isinstance(stage, Mapping) or not is_nonempty_string(stage.get("id")):
                failures.append(
                    failure(
                        "acceptance_stage_invalid",
                        path,
                        "stage id is required",
                        "Assign a unique stage id.",
                    )
                )
                continue
            stage_id = stage["id"]
            if stage_id in stage_ids:
                failures.append(
                    failure(
                        "acceptance_stage_duplicate",
                        f"{path}.id",
                        f"duplicate stage id: {stage_id}",
                        "Keep stage ids unique.",
                    )
                )
            stage_ids.add(stage_id)
            checks = stage.get("checks")
            if not isinstance(checks, list) or not checks:
                failures.append(
                    failure(
                        "acceptance_checks_missing",
                        f"{path}.checks",
                        "stage checks must be non-empty",
                        "Choose checks that match this stage.",
                    )
                )
            else:
                unknown = sorted(
                    str(check)
                    for check in checks
                    if not isinstance(check, str) or check not in _KNOWN_CHECKS
                )
                if unknown:
                    failures.append(
                        failure(
                            "acceptance_checks_unknown",
                            f"{path}.checks",
                            f"unknown checks: {', '.join(unknown)}",
                            "Use the controlled checks documented in STANDARD.md.",
                            checks=unknown,
                        )
                    )
    for field in ("max_corrections_per_stage", "max_total_corrections"):
        value_at_field = value.get(field)
        if (
            not isinstance(value_at_field, int)
            or isinstance(value_at_field, bool)
            or value_at_field < 1
        ):
            failures.append(
                failure(
                    "correction_cap_invalid",
                    f"acceptance.{field}",
                    f"{field} must be a positive integer",
                    "Set an explicit bounded correction cap.",
                )
            )
    per_stage = value.get("max_corrections_per_stage")
    total = value.get("max_total_corrections")
    if (
        isinstance(per_stage, int)
        and not isinstance(per_stage, bool)
        and isinstance(total, int)
        and not isinstance(total, bool)
        and total < per_stage
    ):
        failures.append(
            failure(
                "correction_caps_incoherent",
                "acceptance.max_total_corrections",
                "total correction cap is lower than the per-stage cap",
                "Set max_total_corrections greater than or equal to the per-stage cap.",
            )
        )


@skill_entry
def validate_spec(spec: dict, strict_quality: bool = True, **kwargs) -> dict:
    """Return a pass/fail quality gate; validation failures are not transport errors."""
    failures: list[dict[str, Any]] = []
    if not isinstance(spec, Mapping):
        failures.append(
            failure(
                "spec_invalid",
                "spec",
                "spec must be an object",
                "Start from get_spec_template and fill its sections.",
            )
        )
        return skill_success("Modeling spec failed validation", passed=False, failures=failures)

    if spec.get("spec_version") != "2.0":
        failures.append(
            failure(
                "spec_version_invalid",
                "spec_version",
                "spec_version must equal 2.0",
                "Regenerate the template and migrate the spec to v2.",
            )
        )
    asset = spec.get("asset")
    if (
        not isinstance(asset, Mapping)
        or not is_nonempty_string(asset.get("name"))
        or not is_nonempty_string(asset.get("linear_unit"))
    ):
        failures.append(
            failure(
                "asset_identity_missing",
                "asset",
                "asset name and linear unit are required",
                "Declare a stable asset name and measurement unit.",
            )
        )

    parts = _require_list(spec, "parts", failures, nonempty=strict_quality)
    part_ids = _validate_parts(parts, failures)
    never = _require_list(spec, "never", failures, nonempty=strict_quality)
    if never and not all(is_nonempty_string(item) for item in never):
        failures.append(
            failure(
                "never_invalid",
                "never",
                "NEVER constraints must be non-empty strings",
                "Rewrite each constraint as one explicit prohibited outcome.",
            )
        )
    proportions = _require_list(spec, "proportions", failures, nonempty=strict_quality)
    _validate_proportions(proportions, failures)
    _validate_hierarchy(spec.get("hierarchy"), parts, part_ids, failures)
    materials = _require_list(spec, "materials", failures, nonempty=strict_quality)
    _validate_materials(materials, part_ids, failures)

    priorities = _require_list(spec, "quality_priority", failures, nonempty=strict_quality)
    if priorities and (
        not all(is_nonempty_string(item) for item in priorities)
        or len(priorities) != len(set(priorities))
    ):
        failures.append(
            failure(
                "quality_priority_invalid",
                "quality_priority",
                "quality priorities must be unique non-empty strings",
                "Order the trade-offs from most to least important.",
            )
        )
    if strict_quality and len(priorities) < 3:
        failures.append(
            failure(
                "quality_priority_shallow",
                "quality_priority",
                "strict quality requires at least three ordered priorities",
                "Add the major trade-offs that guide review.",
            )
        )

    uncertainties = spec.get("uncertainties")
    if not isinstance(uncertainties, list):
        failures.append(
            failure(
                "uncertainties_missing",
                "uncertainties",
                "uncertainties must be an array",
                "Record unresolved questions or use an empty array after resolving all of them.",
            )
        )
    else:
        for index, item in enumerate(uncertainties):
            if (
                not isinstance(item, Mapping)
                or not is_nonempty_string(item.get("question"))
                or not is_nonempty_string(item.get("resolution"))
                or not isinstance(item.get("blocking"), bool)
            ):
                failures.append(
                    failure(
                        "uncertainty_invalid",
                        f"uncertainties[{index}]",
                        "uncertainty requires question, resolution, and blocking",
                        "Record how the uncertainty will be resolved before the relevant stage.",
                    )
                )

    _validate_acceptance(spec.get("acceptance"), failures)
    passed = not failures
    return skill_success(
        "Modeling spec passed strict validation"
        if passed
        else f"Modeling spec failed {len(failures)} check(s)",
        passed=passed,
        failures=failures,
        part_count=len(part_ids),
        material_count=len(materials),
        strict_quality=bool(strict_quality),
    )

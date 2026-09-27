"""Validation for the modeling-spec outcome-level recipe pack (PIP-3710 P0-C).

The ``modeling-spec`` skill ships a ``RECIPES.yaml`` recipe pack registered
with the ``dcc-mcp-core`` recipe runtime through the ``metadata.dcc-mcp.recipes``
frontmatter key, so ``recipes__list`` / ``recipes__get`` / ``recipes__validate``
and ``recipes__apply`` can serve it.

This module asserts the pack is:

* loadable by the real core recipe runtime (A1);
* published with Draft 2020-12 ``inputs_schema`` and ``output_contract`` schemas
  that carry ``required`` (A2, A3);
* routed only through ``tool_routing`` or an explicit scripting fallback, with
  every ``${param}`` placeholder naming a required or defaulted input (A4);
* carrying an ``undo`` contract from the P0-B enum with concrete rollback steps
  (A5);
* carrying at least three natural-language ``examplePrompts`` and at least one
  executable ``recovery`` entry (A6).

The negative half matters as much as the positive half: ``validate_recipe_entry``
is the single gate used by both, so every acceptance rule is proven to *fail* on
a mutated copy rather than merely being described here.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml
from jsonschema import Draft202012Validator, ValidationError

SKILL_DIR = Path(__file__).resolve().parents[1] / "skill" / "modeling-spec"
RECIPES_PATH = SKILL_DIR / "RECIPES.yaml"
SKILL_MD_PATH = SKILL_DIR / "SKILL.md"

EXPECTED_RECIPES = ["asset_ingest"]

#: The P0-B enum. Recipe-level `undo` reuses it verbatim so both converge on one
#: vocabulary once P0-B lands in the marketplace schema.
UNDO_ENUM = {"single-step", "none", "manual"}

#: Recovery `next` values that are no-ops rather than executable steps.
NO_OP_RECOVERY = {"retry", "try again", "re-run", "rerun"}

#: Keys of `output_contract.properties` that count as mechanically checkable
#: evidence: a count, a digest, a produced artifact path, or a boolean const.
EVIDENCE_PATTERN = re.compile(r"count|sha|digest|hash|path", re.IGNORECASE)

PLACEHOLDER_PATTERN = re.compile(r"\$\{([^}]+)\}")

_SPEC: dict[str, Any] = {
    "spec_version": "2.0",
    "asset": {
        "name": "Scout Rotorcraft",
        "linear_unit": "cm",
        "purpose": "review",
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
        "stages": [{"id": "ingest", "checks": ["uv_coverage", "material_bindings"]}],
        "max_corrections_per_stage": 3,
        "max_total_corrections": 8,
    },
}

_SCENE: dict[str, Any] = {
    "parts": [
        {
            "id": "hull",
            "parent": "asset_root",
            "pivot": "asset_root",
            "material_slots": ["hull_mat"],
        }
    ],
    "meshes": [
        {
            "part_id": "hull",
            "uv_coverage": 0.94,
            "unbound_material_slots": 0,
            "non_manifold_edges": 0,
            "euler_characteristic": 2,
        },
    ],
    "proportions": {},
}

#: One fully materialized input payload per recipe.
VALID_INPUTS: dict[str, dict[str, Any]] = {
    "asset_ingest": {
        "source_path": "/proj/inbox/scout.glb",
        "asset_name": "Scout Rotorcraft",
        "linear_unit": "cm",
        "report_path": "/proj/reports/scout-ingest.json",
        "spec": _SPEC,
        "scene": _SCENE,
    },
}

#: One observed receipt per recipe that satisfies its `output_contract`.
SAMPLE_RECEIPTS: dict[str, dict[str, Any]] = {
    "asset_ingest": {
        "asset_name": "Scout Rotorcraft",
        "normalized_linear_unit": "cm",
        "imported_mesh_count": 1,
        "source_sha256": "a" * 64,
        "report_path": "/proj/reports/scout-ingest.json",
        "report_sha256": "b" * 64,
        "unbound_material_slots": 0,
        "uv_coverage_min": 0.94,
        "spec_passed": True,
        "scene_passed": True,
        "material_bindings": [{"part_id": "hull", "material_id": "hull_mat", "bound": True}],
        "findings": [],
    },
}


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def pack_document() -> dict[str, Any]:
    return yaml.safe_load(RECIPES_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def recipes_by_name(pack_document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    recipes = pack_document.get("recipes")
    assert isinstance(recipes, list), "pack must declare a `recipes:` list"
    return {recipe["name"]: recipe for recipe in recipes}


def _routed_verbs(pack_document: dict[str, Any]) -> set[str]:
    return set(pack_document["tool_routing"]["tools"])


# ── The shared gate ───────────────────────────────────────────────────────


def _placeholder_errors(
    recipe_name: str,
    where: str,
    values: dict[str, Any],
    properties: dict[str, Any],
    required_inputs: set[str],
) -> list[str]:
    """Every ``${param}`` must name an input that is required or defaulted.

    Core returns steps verbatim and applies no schema defaults, so a placeholder
    pointing at an optional input without a default could never be materialized.
    """
    errors = []
    for key, value in values.items():
        if not isinstance(value, str):
            continue
        for param in PLACEHOLDER_PATTERN.findall(value):
            if param not in properties:
                errors.append(f"{recipe_name}: {where} '{key}' references unknown input '{param}'")
            elif param not in required_inputs and "default" not in (properties[param] or {}):
                errors.append(f"{recipe_name}: {where} '${{{param}}}' has no required/default")
    return errors


def validate_recipe_entry(entry: dict[str, Any], *, routed_verbs: set[str]) -> list[str]:
    """Return the A2-A6 acceptance violations of one recipe entry.

    Both the positive and the negative halves of this module call this gate, so
    a rule that cannot fail is impossible to hide here.
    """
    errors: list[str] = []
    name = entry.get("name") or "<unnamed>"
    schema = entry.get("inputs_schema") if isinstance(entry.get("inputs_schema"), dict) else {}
    properties = schema.get("properties") or {}
    required_inputs = set(schema.get("required") or [])

    # A2 — Draft 2020-12 object inputs_schema with required.
    if schema.get("type") != "object":
        errors.append(f"{name}: inputs_schema must be a Draft 2020-12 object")
    elif "required" not in schema:
        errors.append(f"{name}: inputs_schema must declare `required`")

    # A3 — an output_contract that can actually fail.
    contract = entry.get("output_contract")
    if not isinstance(contract, dict) or contract.get("type") != "object":
        errors.append(f"{name}: output_contract must be a Draft 2020-12 object")
        contract = {}
    else:
        if not contract.get("required"):
            errors.append(f"{name}: output_contract can never fail without `required`")
        contract_properties = contract.get("properties") or {}
        has_evidence = any(
            EVIDENCE_PATTERN.search(key) or (isinstance(value, dict) and "const" in value)
            for key, value in contract_properties.items()
        )
        if not has_evidence:
            errors.append(
                f"{name}: output_contract needs at least one count/hash/path/const evidence field"
            )

    # A4 — routed steps and resolvable placeholders.
    steps = entry.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append(f"{name}: steps must be a non-empty list")
        steps = []
    for step in steps:
        if not isinstance(step, dict):
            errors.append(f"{name}: step must be a mapping")
            continue
        tool = step.get("tool")
        verb = tool.split("__", 1)[1] if isinstance(tool, str) and "__" in tool else None
        if verb not in routed_verbs:
            errors.append(f"{name}: step tool '{tool}' is not declared in tool_routing")
        errors.extend(
            _placeholder_errors(
                name, "step", step.get("arguments") or {}, properties, required_inputs
            ),
        )

    # A5 — undo contract from the P0-B enum, with concrete rollback steps.
    undo = entry.get("undo")
    if undo not in UNDO_ENUM:
        errors.append(f"{name}: undo must be one of {sorted(UNDO_ENUM)}, got {undo!r}")
    undo_steps = [str(step) for step in (entry.get("undo_steps") or [])]
    if undo in {"single-step", "manual"} and not any(step.strip() for step in undo_steps):
        errors.append(f"{name}: undo={undo} requires concrete undo_steps")
    errors.extend(
        _placeholder_errors(
            name,
            "undo_step",
            {f"step_{index}": step for index, step in enumerate(undo_steps)},
            properties,
            required_inputs,
        ),
    )

    # A6 — examplePrompts and executable recovery.
    prompts = entry.get("examplePrompts") or []
    if len(prompts) < 3:
        errors.append(f"{name}: needs at least 3 examplePrompts")
    for prompt in prompts:
        if not isinstance(prompt, str) or len(prompt) < 8 or " " not in prompt:
            errors.append(f"{name}: examplePrompt is not a natural-language sentence: {prompt!r}")
        elif "__" in prompt:
            errors.append(f"{name}: examplePrompt must not list tool names: {prompt!r}")
    recoveries = entry.get("recovery") or []
    if not recoveries:
        errors.append(f"{name}: needs at least one recovery entry")
    for recovery in recoveries:
        when = str((recovery or {}).get("when") or "").strip()
        next_step = str((recovery or {}).get("next") or "").strip()
        if not when:
            errors.append(f"{name}: recovery entry has an empty `when`")
        if not next_step:
            errors.append(f"{name}: recovery entry has an empty `next`")
        elif next_step.lower() in NO_OP_RECOVERY:
            errors.append(f"{name}: recovery `next` is a no-op: {next_step!r}")
    return errors


# ── A1 — visible to the core recipe runtime ───────────────────────────────


def test_pack_declares_expected_recipes(recipes_by_name: dict[str, dict[str, Any]]) -> None:
    assert sorted(recipes_by_name) == EXPECTED_RECIPES


def test_pack_shape_matches_the_core_recipe_pack_contract(pack_document: dict[str, Any]) -> None:
    """Mirror core `load_recipe_pack`'s own guards, with no core installed.

    core silently returns ``[]`` for a pack it cannot read, so a pack that is
    invisible to ``recipes__list`` looks identical to a missing one.
    """
    assert RECIPES_PATH.suffix == ".yaml" and RECIPES_PATH.is_file()
    assert isinstance(pack_document.get("recipes"), list)
    for item in pack_document["recipes"]:
        assert str(item.get("name") or "").strip(), "core skips entries without a name"
        assert isinstance(item.get("steps"), list)
        assert isinstance(item.get("inputs_schema"), dict)
        assert isinstance(item.get("output_contract"), dict)


def test_core_recipe_runtime_loads_the_pack() -> None:
    """core `load_recipe_pack` must return the recipe, or recipes__get cannot see it."""
    pytest.importorskip("dcc_mcp_core")
    from dcc_mcp_core.recipes import load_recipe_pack

    loaded = load_recipe_pack(str(RECIPES_PATH), skill_name="modeling-spec")
    assert [recipe.name for recipe in loaded] == EXPECTED_RECIPES
    assert set(loaded[0].inputs_schema["required"]) == {
        "source_path",
        "asset_name",
        "linear_unit",
        "report_path",
        "spec",
        "scene",
    }
    assert loaded[0].output_contract["required"], "core must see a failing output_contract"
    assert len(loaded[0].steps) == 5, "the ingest plan must stay a five-step dispatch"


def test_core_lists_the_recipe_through_skill_metadata() -> None:
    """recipes__list / recipes__get resolution path, without a live server."""
    pytest.importorskip("dcc_mcp_core")
    from dcc_mcp_core.recipes import find_recipe_entry, list_recipe_entries

    class _Metadata:
        name = "modeling-spec"
        skill_path = str(SKILL_DIR)
        metadata: dict[str, Any] = {
            "dcc-mcp": {"dcc": "multi-dcc", "tools": "tools.yaml", "recipes": "RECIPES.yaml"},
        }

    entries = list_recipe_entries(_Metadata())
    assert [entry["name"] for entry in entries] == EXPECTED_RECIPES
    found = find_recipe_entry(_Metadata(), "asset_ingest")
    assert found is not None and found["provenance"]["format"] == "recipe-pack"


def _frontmatter() -> dict[str, Any]:
    text = SKILL_MD_PATH.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "SKILL.md has no YAML frontmatter"
    end = text.index("\n---\n", 3)
    return yaml.safe_load(text[4:end])


def test_skill_still_passes_core_skill_validation() -> None:
    """The new frontmatter keys must not break the core skill contract check."""
    validate_skill = pytest.importorskip("dcc_mcp_core").validate_skill

    report = validate_skill(str(SKILL_DIR))
    assert not report.has_errors, report


def test_skill_frontmatter_declares_and_mirrors_the_recipe_pack() -> None:
    dcc_mcp = _frontmatter().get("metadata", {}).get("dcc-mcp", {})
    assert dcc_mcp.get("recipes") == "RECIPES.yaml"
    mirrored = dcc_mcp.get("recipes_undo")
    assert mirrored, "SKILL.md must mirror the recipe-level undo enum"
    for recipe_name, undo in mirrored.items():
        assert recipe_name in EXPECTED_RECIPES, (
            f"SKILL.md mirrors an unknown recipe '{recipe_name}'"
        )
        assert undo in UNDO_ENUM, f"SKILL.md mirror for '{recipe_name}' is outside the P0-B enum"


def test_skill_frontmatter_undo_mirror_matches_the_pack(
    recipes_by_name: dict[str, dict[str, Any]],
) -> None:
    mirrored = _frontmatter()["metadata"]["dcc-mcp"]["recipes_undo"]
    for recipe_name, undo in mirrored.items():
        assert recipes_by_name[recipe_name]["undo"] == undo, (
            f"SKILL.md mirror for '{recipe_name}' drifted from RECIPES.yaml"
        )


# ── A2/A3 — schemas that can fail ─────────────────────────────────────────


@pytest.mark.parametrize("recipe_name", EXPECTED_RECIPES)
def test_inputs_schema_is_a_draft_2020_12_object_with_required(
    recipes_by_name: dict[str, dict[str, Any]],
    recipe_name: str,
) -> None:
    schema = recipes_by_name[recipe_name]["inputs_schema"]
    Draft202012Validator.check_schema(schema)
    assert schema["type"] == "object"
    assert schema["required"], f"{recipe_name} inputs_schema has no required fields"
    Draft202012Validator(schema).validate(VALID_INPUTS[recipe_name])


@pytest.mark.parametrize("recipe_name", EXPECTED_RECIPES)
def test_output_contract_is_a_draft_2020_12_object_with_required(
    recipes_by_name: dict[str, dict[str, Any]],
    recipe_name: str,
) -> None:
    contract = recipes_by_name[recipe_name]["output_contract"]
    Draft202012Validator.check_schema(contract)
    assert contract["type"] == "object"
    assert contract["required"], f"{recipe_name} contract can never fail without required fields"


@pytest.mark.parametrize("recipe_name", EXPECTED_RECIPES)
def test_output_contract_carries_failing_evidence(
    recipes_by_name: dict[str, dict[str, Any]],
    recipe_name: str,
) -> None:
    """A contract that only asserts `success: true` would be a soft assertion."""
    contract = recipes_by_name[recipe_name]["output_contract"]
    evidence = [
        key
        for key, value in contract["properties"].items()
        if EVIDENCE_PATTERN.search(key) or (isinstance(value, dict) and "const" in value)
    ]
    assert evidence, f"{recipe_name} output_contract has no count/hash/path/const evidence field"
    assert len(contract["required"]) > 1, f"{recipe_name} contract must require more than one field"


@pytest.mark.parametrize("recipe_name", EXPECTED_RECIPES)
def test_output_contract_accepts_a_valid_receipt(
    recipes_by_name: dict[str, dict[str, Any]],
    recipe_name: str,
) -> None:
    Draft202012Validator(recipes_by_name[recipe_name]["output_contract"]).validate(
        SAMPLE_RECEIPTS[recipe_name]
    )


@pytest.mark.parametrize("recipe_name", EXPECTED_RECIPES)
def test_output_contract_rejects_an_ingest_that_imported_nothing(
    recipes_by_name: dict[str, dict[str, Any]],
    recipe_name: str,
) -> None:
    """A receipt reporting success without geometry must fail its contract."""
    contract = recipes_by_name[recipe_name]["output_contract"]
    receipt = SAMPLE_RECEIPTS[recipe_name]
    with pytest.raises(ValidationError):
        Draft202012Validator(contract).validate({**receipt, "imported_mesh_count": 0})


def test_output_contract_rejects_a_failed_gate_or_a_broken_digest(
    recipes_by_name: dict[str, dict[str, Any]],
) -> None:
    contract = recipes_by_name["asset_ingest"]["output_contract"]
    receipt = SAMPLE_RECEIPTS["asset_ingest"]
    # A failed gate is a valid, reportable outcome, so the contract must not
    # reject it; what it must reject is a receipt that did not measure or write
    # anything. `spec_passed: false` passing here is deliberate.
    broken_receipts = [
        {**receipt, "report_sha256": "not-a-digest"},
        {**receipt, "source_sha256": "not-a-digest"},
        {**receipt, "normalized_linear_unit": "parsec"},
        {**receipt, "uv_coverage_min": 1.5},
        {key: value for key, value in receipt.items() if key != "uv_coverage_min"},
    ]
    for broken in broken_receipts:
        with pytest.raises(ValidationError):
            Draft202012Validator(contract).validate(broken)


# ── A4 — routing and placeholder materialization ──────────────────────────


@pytest.mark.parametrize("recipe_name", EXPECTED_RECIPES)
def test_steps_are_routed_or_declared_scripting_fallback(
    recipes_by_name: dict[str, dict[str, Any]],
    pack_document: dict[str, Any],
    recipe_name: str,
) -> None:
    routing = pack_document["tool_routing"]
    adapters = set(routing["adapters"])
    assert set(routing["scripting_fallback"]) == adapters
    for step in recipes_by_name[recipe_name]["steps"]:
        tool = step["tool"]
        verb = tool.split("__", 1)[1]
        assert verb in routing["tools"], f"{recipe_name} dispatches unrouted verb '{verb}'"
        per_adapter = routing["tools"][verb]
        assert set(per_adapter) == adapters, f"'{verb}' routing does not cover every adapter"
        # Every adapter either publishes a concrete tool or resolves to the
        # adapter's declared scripting fallback — nothing is silently dropped.
        for adapter in adapters:
            if per_adapter.get(adapter) is None:
                assert routing["scripting_fallback"][adapter], (
                    f"'{verb}' has no tool and no scripting fallback on {adapter}"
                )


@pytest.mark.parametrize("recipe_name", EXPECTED_RECIPES)
def test_placeholders_resolve_to_required_or_defaulted_inputs(
    recipes_by_name: dict[str, dict[str, Any]],
    recipe_name: str,
) -> None:
    recipe = recipes_by_name[recipe_name]
    properties = recipe["inputs_schema"]["properties"]
    required = set(recipe["inputs_schema"]["required"])
    for step in recipe["steps"]:
        for key, value in step["arguments"].items():
            if not (isinstance(value, str) and value.startswith("${") and value.endswith("}")):
                continue
            param = value[2:-1]
            assert param in properties, (
                f"{recipe_name} step argument '{key}' references unknown input '{param}'"
            )
            assert param in required or "default" in properties[param], (
                f"{recipe_name} placeholder '${{{param}}}' is neither required nor defaulted"
            )


@pytest.mark.parametrize("recipe_name", EXPECTED_RECIPES)
def test_undo_step_placeholders_resolve_to_declared_inputs(
    recipes_by_name: dict[str, dict[str, Any]],
    recipe_name: str,
) -> None:
    """Rollback steps must be materializable from the same inputs as the plan."""
    recipe = recipes_by_name[recipe_name]
    properties = recipe["inputs_schema"]["properties"]
    required = set(recipe["inputs_schema"]["required"])
    for undo_step in recipe["undo_steps"]:
        for param in PLACEHOLDER_PATTERN.findall(str(undo_step)):
            assert param in properties, (
                f"{recipe_name} undo step references unknown input '{param}'"
            )
            assert param in required or "default" in properties[param], (
                f"{recipe_name} undo step '${{{param}}}' is neither required nor defaulted"
            )


# ── A5/A6 — undo, prompts, recovery ───────────────────────────────────────


@pytest.mark.parametrize("recipe_name", EXPECTED_RECIPES)
def test_recipe_declares_undo_from_the_p0b_enum(
    recipes_by_name: dict[str, dict[str, Any]],
    recipe_name: str,
) -> None:
    recipe = recipes_by_name[recipe_name]
    assert recipe["undo"] in UNDO_ENUM
    assert recipe["undo_steps"], f"{recipe_name} must spell out its rollback steps"


@pytest.mark.parametrize("recipe_name", EXPECTED_RECIPES)
def test_recipe_declares_prompts_and_recovery(
    recipes_by_name: dict[str, dict[str, Any]],
    recipe_name: str,
) -> None:
    recipe = recipes_by_name[recipe_name]
    prompts = recipe["examplePrompts"]
    assert len(prompts) >= 3
    for prompt in prompts:
        assert isinstance(prompt, str) and len(prompt) >= 8 and " " in prompt
        assert "__" not in prompt, f"{recipe_name} prompt lists a tool name: {prompt}"
    recoveries = recipe["recovery"]
    assert len(recoveries) >= 1
    for recovery in recoveries:
        assert recovery["when"].strip()
        assert recovery["next"].strip()


# ── Negative half: every rule above must be able to fail ──────────────────

NEGATIVE_CASES: dict[str, Callable[[dict[str, Any]], None]] = {
    "missing_undo": lambda e: e.pop("undo"),
    "undo_outside_enum": lambda e: e.update(undo="maybe"),
    "undo_without_steps": lambda e: e.update(undo="manual", undo_steps=[]),
    "output_contract_without_required": lambda e: e["output_contract"].pop("required"),
    "output_contract_soft_success_only": lambda e: e.update(
        output_contract={
            "type": "object",
            "required": ["success"],
            "properties": {"success": {"type": "boolean"}},
        },
    ),
    "inputs_schema_without_required": lambda e: e["inputs_schema"].pop("required"),
    "unrouted_step_tool": lambda e: e["steps"].append(
        {"tool": "asset_ingest__not_routed", "arguments": {}}
    ),
    "dangling_placeholder": lambda e: e["steps"][0]["arguments"].update(
        asset_name="${not_an_input}"
    ),
    "optional_placeholder_without_default": lambda e: (
        e["inputs_schema"]["properties"].update(optional_no_default={"type": "string"}),
        e["steps"][0]["arguments"].update(note="${optional_no_default}"),
    ),
    "undo_step_dangling_placeholder": lambda e: e.update(undo_steps=["delete ${nope}"]),
    "too_few_prompts": lambda e: e.update(examplePrompts=["Check this scene"]),
    "tool_listing_prompt": lambda e: e.update(
        examplePrompts=e["examplePrompts"][:2] + ["run asset_ingest__normalize_scene"],
    ),
    "empty_recovery_next": lambda e: e.update(recovery=[{"when": "the scan fails", "next": "   "}]),
    "retry_only_recovery": lambda e: e.update(recovery=[{"when": "it fails", "next": "retry"}]),
    "no_recovery": lambda e: e.update(recovery=[]),
}


@pytest.mark.parametrize("recipe_name", EXPECTED_RECIPES)
def test_gate_accepts_the_shipped_recipes(
    recipes_by_name: dict[str, dict[str, Any]],
    pack_document: dict[str, Any],
    recipe_name: str,
) -> None:
    assert (
        validate_recipe_entry(
            recipes_by_name[recipe_name], routed_verbs=_routed_verbs(pack_document)
        )
        == []
    )


@pytest.mark.parametrize("case", sorted(NEGATIVE_CASES))
def test_negative_cases_do_fail(case: str, pack_document: dict[str, Any]) -> None:
    """Each acceptance rule must be able to fail, not merely be described."""
    entry = copy.deepcopy(next(r for r in pack_document["recipes"] if r["name"] == "asset_ingest"))
    NEGATIVE_CASES[case](entry)
    errors = validate_recipe_entry(entry, routed_verbs=_routed_verbs(pack_document))
    assert errors, f"negative case '{case}' was accepted by the gate"

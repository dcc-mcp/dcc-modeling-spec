"""RECIPES.yaml owns the contract fields; core's runtime drops them.

``undo``, ``examplePrompts`` and ``recovery`` are declared by this pack, but
core's ``load_recipe_pack()`` builds a frozen ``RecipeDefinition`` modelling a
fixed field set, so the payload ``recipes__list`` / ``recipes__get`` serve
silently loses them: no error, no warning, and nothing in CI noticed.

This module pins that gap instead of hiding it:

* :func:`test_pack_declares_the_contract_fields` reads RECIPES.yaml directly,
  keeping the pack the source of truth: a regression in the pack fails the
  suite even when core is unavailable.
* :func:`test_core_serves_the_contract_fields` fails while core drops the
  fields. It is marked ``xfail(strict=True)`` so the suite stays green until
  the core-side decision on passing them through is taken, and so the marker
  turns an unexpected pass into a failure the moment core starts serving them
  -- the signal to delete the marker and keep the assertion as a permanent
  contract.

PyYAML and dcc-mcp-core are imported at module scope on purpose: a missing
dependency is a collection error that fails the suite, never a silent skip of
the only check that can see the gap.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from dcc_mcp_core.recipes import load_recipe_pack

SKILL_NAME = "modeling-spec"
SKILL_DIR = Path(__file__).resolve().parents[1] / "skill" / SKILL_NAME
RECIPES_PATH = SKILL_DIR / "RECIPES.yaml"

#: The fields this pack declares and core's `RecipeDefinition` does not model.
CONTRACT_FIELDS = ("undo", "examplePrompts", "recovery")

#: The P0-B enum. Recipe-level `undo` reuses it verbatim.
UNDO_ENUM = {"single-step", "none", "manual"}

#: Recovery `next` values that are no-ops rather than executable steps.
NO_OP_RECOVERY = {"retry", "try again", "re-run", "rerun"}


def _declared_entries() -> list[dict[str, Any]]:
    """Read RECIPES.yaml directly: the pack is the source of truth."""
    document = yaml.safe_load(RECIPES_PATH.read_text(encoding="utf-8"))
    recipes = (document or {}).get("recipes")
    assert isinstance(recipes, list) and recipes, f"{RECIPES_PATH} declares no recipes"
    return recipes


def _served_entries() -> dict[str, dict[str, Any]]:
    """The payload core's recipe runtime serves, keyed by recipe name."""
    loaded = load_recipe_pack(str(RECIPES_PATH), skill_name=SKILL_NAME)
    return {definition.name: definition.to_dict() for definition in loaded}


def test_pack_declares_the_contract_fields() -> None:
    """Every recipe must carry the undo / prompt / recovery contract."""
    for entry in _declared_entries():
        name = entry.get("name") or "<unnamed>"
        missing = [field for field in CONTRACT_FIELDS if field not in entry]
        assert not missing, f"{name}: RECIPES.yaml is missing {sorted(missing)}"

        undo = entry["undo"]
        assert undo in UNDO_ENUM, f"{name}: undo={undo!r} outside {sorted(UNDO_ENUM)}"
        assert entry.get("undo_steps"), f"{name}: undo={undo!r} needs undo_steps"

        prompts = entry["examplePrompts"]
        assert len(prompts) >= 3, f"{name}: needs 3 examplePrompts, got {len(prompts)}"
        for prompt in prompts:
            assert isinstance(prompt, str) and " " in prompt, (
                f"{name}: examplePrompt is not a sentence: {prompt!r}"
            )
            assert "__" not in prompt, f"{name}: prompt lists a tool: {prompt!r}"

        recoveries = entry["recovery"]
        assert recoveries, f"{name}: needs at least one recovery entry"
        for recovery in recoveries:
            when = str(recovery.get("when") or "").strip()
            next_step = str(recovery.get("next") or "").strip()
            assert when, f"{name}: recovery entry has an empty `when`"
            assert next_step, f"{name}: recovery entry has an empty `next`"
            assert next_step.lower() not in NO_OP_RECOVERY, (
                f"{name}: recovery `next` is a no-op: {next_step!r}"
            )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "core's RecipeDefinition does not model undo / examplePrompts / recovery, "
        "so load_recipe_pack() drops them from the payload recipes__list and "
        "recipes__get serve. Delete this marker once core round-trips them; "
        "strict=True fails the suite when it unexpectedly starts passing."
    ),
)
def test_core_serves_the_contract_fields() -> None:
    """The payload core serves must round-trip every contract field."""
    served = _served_entries()
    problems: list[str] = []
    for entry in _declared_entries():
        name = entry.get("name") or "<unnamed>"
        if name not in served:
            problems.append(f"{name}: core's runtime does not serve this recipe")
            continue
        payload = served[name]
        dropped = [field for field in CONTRACT_FIELDS if field not in payload]
        altered = [
            f"{field}: yaml={entry[field]!r} core={payload[field]!r}"
            for field in CONTRACT_FIELDS
            if field in payload and payload[field] != entry.get(field)
        ]
        if dropped or altered:
            problems.append(f"{name}: dropped={dropped} altered={altered}")
    assert not problems, (
        "core does not round-trip the recipe contract fields: "
        + "; ".join(problems)
        + f" (core serves {sorted(served)})"
    )

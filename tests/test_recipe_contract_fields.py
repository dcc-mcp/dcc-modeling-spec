"""Characterize how core loses this pack's contract fields, and trip when it changes.

`undo`, `examplePrompts` and `recovery` are declared by this pack, but core's
`load_recipe_pack()` builds a frozen `RecipeDefinition` modelling a fixed field
set, so the payload `recipes__list` / `recipes__get` serve silently loses them.

Two assertions pin that loss instead of hiding it:

* :func:`test_core_recipe_field_loss_is_characterized` records the exact set of
  fields core loses today, so the loss is judged on every run. It is green while
  the loss is unchanged and turns red the moment core drops another field,
  rewrites a value, or starts passing these through.
* :func:`test_core_serves_the_contract_fields` is the round-trip tripwire. It
  fails while core drops the fields and, being strict, reports as an expected
  failure; the moment core round-trips them it turns red, which is the signal
  to delete the marker.

:func:`test_field_loss_comparator_catches_a_new_drop` guards the comparator the
two assertions share, so neither can pass by comparing nothing.

Neither assertion patches core nor prejudges whether core should pass the fields
through; they only make the loss observable. The pack-side contract itself (undo
enum, prompt and recovery shape) is covered by this repository's recipe tests
and their `NEGATIVE_CASES`. PyYAML and dcc-mcp-core are imported at module
scope: a missing dependency is a collection error, never a silent skip of the
only check that can see the gap.
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
CONTRACT_FIELDS = ("examplePrompts", "recovery", "undo")

#: What core 0.20.x loses from the served payload today: the three contract
#: fields plus the two pack-only keys that spell the undo contract out.
KNOWN_CORE_DROP = ("examplePrompts", "recovery", "side_effects", "undo", "undo_steps")


def _direct_entries() -> dict[str, dict[str, Any]]:
    """Read RECIPES.yaml directly: the pack is the source of truth."""
    document = yaml.safe_load(RECIPES_PATH.read_text(encoding="utf-8"))
    recipes = (document or {}).get("recipes")
    assert isinstance(recipes, list) and recipes, f"{RECIPES_PATH} declares no recipes"
    return {entry["name"]: entry for entry in recipes}


def _served_entries() -> dict[str, dict[str, Any]]:
    """The payload core's recipe runtime serves, keyed by recipe name."""
    loaded = load_recipe_pack(str(RECIPES_PATH), skill_name=SKILL_NAME)
    return {definition.name: definition.to_dict() for definition in loaded}


def _field_loss(
    direct: dict[str, Any],
    served: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Return the fields core dropped, and the fields whose value it rewrote."""
    dropped = sorted(set(direct) - set(served))
    shared = set(direct) & set(served)
    altered = sorted(k for k in shared if direct[k] != served[k])
    return dropped, altered


def test_core_recipe_field_loss_is_characterized() -> None:
    """core must lose exactly the known fields -- no more, no less."""
    served = _served_entries()
    for name, direct in _direct_entries().items():
        dropped, altered = _field_loss(direct, served[name])
        assert dropped == list(KNOWN_CORE_DROP), (
            f"{name}: drop set changed -> {dropped} (known: {list(KNOWN_CORE_DROP)})"
        )
        assert altered == [], f"{name}: core rewrote field values -> {altered}"


@pytest.mark.xfail(
    raises=AssertionError,
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
    for name, direct in _direct_entries().items():
        dropped, altered = _field_loss(direct, served[name])
        lost = sorted(f for f in CONTRACT_FIELDS if f in dropped + altered)
        if lost:
            problems.append(f"{name}: {lost}")
    assert not problems, f"core lost {list(CONTRACT_FIELDS)}: " + "; ".join(problems)


def test_field_loss_comparator_catches_a_new_drop() -> None:
    """Guard the comparator: a field core stops serving must be reported."""
    name, direct = next(iter(_direct_entries().items()))
    served = dict(_served_entries()[name])
    served.pop("steps")
    dropped, altered = _field_loss(direct, served)
    assert "steps" in dropped, f"comparator missed a dropped field -> {dropped}"
    assert dropped != list(KNOWN_CORE_DROP), "extra drop must differ from the known set"
    assert altered == [], f"comparator invented an alteration -> {altered}"

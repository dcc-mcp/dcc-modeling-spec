#!/usr/bin/env python3
"""Materialize the ``asset_ingest`` dispatch plan from validated inputs.

``recipes__apply`` returns the plan verbatim: core neither substitutes ``${x}``
placeholders nor applies schema defaults. This script fills both from the
recipe's own ``inputs_schema`` and prints the plan a caller can dispatch, so the
B-class host-run evidence in this directory can be reproduced mechanically.

Usage::

    python examples/asset_ingest/materialize_plan.py --inputs examples/asset_ingest/inputs.example.json
    python examples/asset_ingest/materialize_plan.py --inputs plan-inputs.json --adapter blender

The script performs no host work and never imports a DCC module; it is safe to
run in CI.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RECIPES_PATH = REPO_ROOT / "skill" / "modeling-spec" / "RECIPES.yaml"
PLACEHOLDER_PATTERN = re.compile(r"^\$\{([^}]+)\}$")


def load_pack() -> dict:
    return yaml.safe_load(RECIPES_PATH.read_text(encoding="utf-8"))


def with_defaults(recipe: dict, inputs: dict) -> dict:
    """Apply schema defaults, then report any still-unresolved required input."""
    properties = recipe["inputs_schema"]["properties"]
    required = set(recipe["inputs_schema"].get("required") or [])
    merged = {name: spec["default"] for name, spec in properties.items() if "default" in spec}
    merged.update(inputs)

    unknown = sorted(set(merged) - set(properties))
    if unknown:
        raise SystemExit(f"inputs not declared in inputs_schema: {unknown}")
    missing = sorted(required - set(merged))
    if missing:
        raise SystemExit(f"missing required inputs: {missing}")
    return merged


def materialize(recipe: dict, inputs: dict) -> list[dict]:
    resolved = with_defaults(recipe, inputs)
    steps = []
    for step in recipe["steps"]:
        arguments: dict = {}
        for key, value in (step.get("arguments") or {}).items():
            match = PLACEHOLDER_PATTERN.match(value) if isinstance(value, str) else None
            arguments[key] = resolved[match.group(1)] if match else value
        steps.append({"tool": step["tool"], "arguments": arguments})

    undo_steps = [
        PLACEHOLDER_PATTERN.sub(lambda m: str(resolved[m.group(1)]), str(step)) for step in recipe.get("undo_steps") or []
    ]
    return steps, undo_steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True, type=Path, help="JSON file of recipe inputs")
    parser.add_argument("--adapter", default="blender", help="adapter to resolve tool_routing against")
    parser.add_argument("--recipe", default="asset_ingest", help="recipe name in RECIPES.yaml")
    args = parser.parse_args(argv)

    pack = load_pack()
    recipe = next((r for r in pack["recipes"] if r["name"] == args.recipe), None)
    if recipe is None:
        raise SystemExit(f"unknown recipe '{args.recipe}'")

    inputs = json.loads(args.inputs.read_text(encoding="utf-8"))
    steps, undo_steps = materialize(recipe, inputs)

    routing = pack["tool_routing"]
    fallback = routing["scripting_fallback"].get(args.adapter)
    dispatch = []
    for step in steps:
        verb = step["tool"].split("__", 1)[1]
        tool = routing["tools"][verb].get(args.adapter) or fallback
        dispatch.append({"tool": tool, "arguments": step["arguments"], "via": "tool_routing" if routing["tools"][verb].get(args.adapter) else "scripting_fallback"})

    plan = {
        "recipe": args.recipe,
        "adapter": args.adapter,
        "undo": recipe["undo"],
        "steps": dispatch,
        "undo_steps": undo_steps,
        "output_contract": recipe["output_contract"],
    }
    print(json.dumps(plan, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

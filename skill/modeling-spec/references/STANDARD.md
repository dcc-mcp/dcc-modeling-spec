# Modeling Spec Standard

## State machine

Every task follows this sequence:

1. `draft-spec`
2. `validate-spec`
3. `build-stage`
4. `measure-stage`
5. `validate-stage`
6. `package-review`
7. `choose-action`
8. `complete` or return to one earlier state

Scene authoring is blocked until the strict spec gate passes. A stage is blocked
until the measurements required by its declared checks are present. Validation
failures return to `build-stage` or, with explicit rationale, to `draft-spec`.

## Stage gates

The default template contains:

- `blockout`: required parts, hierarchy, pivots, and numeric proportions;
- `final`: blockout checks plus complete UV coverage, bound material slots,
  non-manifold checks, and expected Euler characteristics.

A project may add stages, but every check must match the work declared for that
stage. Do not require a render, chart, animation, or unrelated presentation gate
from a modeling-only stage.

## Correction loop

After each comparison sheet, choose exactly one typed action:

- `continue`: the current stage passed; advance to the next stage.
- `refine-spec`: references or intent changed; revise and revalidate the spec.
- `refine-build`: keep the spec and perform one bounded correction.
- `request-input`: a blocking uncertainty needs user evidence or a decision.
- `stop`: preserve artifacts and report why the task cannot safely continue.

The spec owns `max_corrections_per_stage` and `max_total_corrections`. Defaults
are 3 and 8. A project may lower or raise them before building based on host cost,
but must never silently increase a cap during the loop.

Stop and request input when any of these occurs:

- two corrections alternate between the same outcomes;
- two consecutive review cycles show no measurable improvement;
- the next change would violate a NEVER constraint;
- the next change would alter an unresolved blocking assumption;
- a required typed measurement or exact host target is unavailable;
- completion is unknown after a destructive or non-idempotent action.

## Evidence package

For each review cycle retain:

- the validated spec and its digest;
- stage id and correction counters;
- measured scene facts and validator result;
- reference and capture identities;
- image-stat results;
- comparison-sheet path and digest;
- the one selected next action and rationale.

The comparison sheet is deterministic packaging. A model or human reviewer may
judge it, but the packaging script must not score resemblance or aesthetics.

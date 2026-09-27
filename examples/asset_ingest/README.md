# `asset_ingest` host-run evidence

Status: **not run on a real host** (B-class, non-blocking).

No DCC host or scene was available on the machine that authored this recipe, so
the deliverable is the plan plus the gate that will judge the receipt — not a
recorded run. Nothing below is a synthesized artifact passed off as a real one.

## What is reproducible today

```bash
python examples/asset_ingest/materialize_plan.py --inputs examples/asset_ingest/inputs.example.json
```

Resolves `tool_routing` for `--adapter`, applies `inputs_schema` defaults,
substitutes every `${x}` placeholder, and prints the five-step dispatch plan
together with the `undo_steps` and the `output_contract` the receipt will be
validated against. No host is required; it runs in CI.

## What a real run must produce

Dispatch the plan to a live instance in order, then validate the observed receipt
against `skill/modeling-spec/RECIPES.yaml` → `recipes[asset_ingest].output_contract`:

| Field | Evidence it carries | Fails when |
|---|---|---|
| `imported_mesh_count` | geometry actually entered the scene (≥1) | the import produced nothing |
| `normalized_linear_unit` | the unit the asset was converted to | the unit conversion never ran |
| `source_sha256` | SHA-256 of the ingest source, `^[0-9a-f]{64}$` | the wrong file was ingested |
| `report_sha256` | SHA-256 of the written material-mapping report | the report was not written or was truncated |
| `uv_coverage_min` | lowest measured UV coverage across meshes | UVs were never measured |
| `unbound_material_slots` | slots left without a material | bindings were skipped rather than reported |
| `spec_passed`, `scene_passed` | both existing gates, reused | either gate failed |

Record here: host and version, the commands in dispatch order, the run log, the
report file, and its `sha256sum`. A run that cannot produce these fields has not
delivered the recipe.

## Rollback

`undo` is `manual`: ingest mutates the scene graph, and a host undo stack alone is
not a reliable rollback across adapters. Close the scene without saving, reopen
the last saved version, then delete the report file.

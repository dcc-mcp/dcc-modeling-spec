---
name: modeling-spec
description: >-
  Define, validate, build, measure, and review structured 3D modeling work across
  Maya, Blender, Houdini, and 3ds Max. Use when a modeling task needs an explicit
  parts checklist, NEVER constraints, numeric proportions, hierarchy and pivot
  ownership, material and UV gates, staged validation, comparison sheets, or a
  bounded correction loop.
license: MIT
compatibility: "dcc-mcp-core 0.19+, Python 3.7+, typed host measurement tools"
allowed-tools: Bash Read Write
metadata:
  dcc-mcp:
    dcc: multi-dcc
    version: "0.1.0"
    layer: domain
    stage: modeling
    tags: [modeling, specification, validation, topology, uv, materials, review]
    search-hint: "modeling spec v2 parts hierarchy pivots proportions UV material validation comparison sheet bounded correction"
    tools: tools.yaml
    references:
      - "references/*.md"
---

# Modeling Spec

Turn a written modeling request into a measurable contract before authoring scene
content. Scripts enforce declared facts; the model judges references, priorities,
and whether a proposed correction preserves the user's intent.

This Skill is host-neutral. It does not execute arbitrary host code, mutate a
scene, score visual quality, or replace typed tools owned by Maya, Blender,
Houdini, or 3ds Max.

## Control path

1. Select one exact DCC instance with `dcc-mcp-cli list`.
2. Use `search -> describe/load-skill -> call` for every host capability.
3. Keep one task session through specification, build, measurement, and review.
4. Fetch a fresh v2 template with `modeling_spec__get_spec_template`.
5. Fill every section and call `modeling_spec__validate_spec` with
   `strict_quality=true`. Do not begin the build while `passed=false`.
6. Build one declared stage with typed tools from the owning adapter.
7. Measure scene facts through read-only host tools, then call
   `modeling_spec__validate_scene_vs_spec` for that stage.
8. Package the reference and bounded views with
   `modeling_spec__make_comparison_sheet`. The artifact is evidence, not a score.
9. Choose exactly one next action: `continue`, `refine-spec`, `refine-build`,
   `request-input`, or `stop`.

Use [STANDARD.md](references/STANDARD.md) for the pass-gated state machine and
bounded correction rules. Use [GLOSSARY.md](references/GLOSSARY.md) when writing
the spec, and [HOST_ROUTING.md](references/HOST_ROUTING.md) to discover measured
facts without hard-coding adapter tool names.

## Modeling Spec v2 contract

- `asset`: stable name, linear unit, purpose, and reference identifiers.
- `parts`: stable part ids, required/optional status, parent, pivot intent, and
  spec-owned expected Euler characteristic for required topology-checked meshes.
- `never`: explicit outcomes that no build or correction may introduce.
- `proportions`: named numeric ratios with tolerances.
- `hierarchy`: one root and parent/pivot ownership for every declared part.
- `materials`: stable material ids, target part slots, and required channels.
- `quality_priority`: ordered trade-offs used when two goals conflict.
- `uncertainties`: questions, resolution path, and blocking state.
- `acceptance`: named stages, matching checks, and bounded correction caps.

`validate_spec` returns `success=true` for a completed validation call and places
the gate result in `context.passed`. A shallow or inconsistent spec is a failed
quality gate, not a transport failure.

## Scene measurement contract

Pass only measured facts to `validate_scene_vs_spec`:

- part id, parent, pivot, and assigned material slots;
- per-mesh UV coverage fraction and unbound material slot count;
- non-manifold edge count;
- measured Euler characteristic; the expected value comes only from the part spec;
- measured values for every declared numeric proportion.

Do not infer missing measurements from a screenshot. The validator fails closed
and reports an actionable `code`, `path`, `message`, and `remediation` for every
missing or mismatched fact.

## Review artifacts

`image_stats` and `make_comparison_sheet` accept bounded, regular 8-bit PNG
files. The codec supports grayscale, RGB, gray-alpha, and RGBA non-interlaced
PNGs and rejects oversized, corrupt, symlinked, or unsupported inputs.

- `image_stats` detects near-uniform black/white frames and checks PNG gamma/sRGB
  metadata against an optional expected color space.
- `make_comparison_sheet` packages one reference plus one to eight captures into
  a labeled sRGB PNG. It never emits a quality score.

## Honest boundaries

- A passing gate proves only that the supplied measured facts satisfy the spec.
  It does not prove the adapter measurements are correct.
- A comparison sheet packages evidence; it does not decide whether the model
  resembles the reference.
- Missing typed measurements belong in the owning adapter. Do not add raw Python,
  host-specific execution, or UI automation to this Skill.
- PNG metadata can prove a declared mismatch. Missing metadata is reported as
  `missing`, not guessed to be correct or broken.
- Real-host validation remains required before claiming a destructive modeling
  workflow completed in Maya, Blender, Houdini, or 3ds Max.

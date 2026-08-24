# DCC Modeling Spec

Cross-DCC specification, validation, and review workflow for Maya, Blender,
Houdini, and 3ds Max.

`modeling-spec` turns modeling intent into a strict v2 contract, validates typed
host measurements at declared stages, detects unusable PNG review captures, and
packages reference/capture sheets without scoring them.

## Install

After the package is published in the DCC-MCP Marketplace:

```powershell
dcc-mcp-cli marketplace install dcc-modeling-spec --dcc maya
```

Replace `maya` with `blender`, `houdini`, or `3dsmax` for the target adapter.

## Agent workflow

1. Load `modeling-spec` and fetch a v2 template.
2. Fill parts, NEVER constraints, proportions, hierarchy/pivots, materials,
   priorities, uncertainties, and staged acceptance.
3. Pass the strict spec gate before building.
4. Build one stage with typed host tools and read back measured facts.
5. Pass the matching scene-vs-spec gate.
6. Package bounded PNG views for review and choose one correction action.

See [SKILL.md](skill/modeling-spec/SKILL.md) for the full contract and honest
boundaries.

## Validate

```powershell
python -m pytest -q
python -m ruff check skill tests
python -m ruff format --check skill tests
python -c "from dcc_mcp_core import validate_skill; r=validate_skill('skill/modeling-spec'); print(r); raise SystemExit(1 if r.has_errors else 0)"
```

## License

MIT. User references and scene assets retain their own licenses.

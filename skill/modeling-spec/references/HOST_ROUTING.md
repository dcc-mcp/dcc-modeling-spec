# Host Routing

Discover capabilities by intent with `dcc-mcp-cli search`, describe the selected
tool, then call its typed schema. Keep tool slugs out of the shared spec.

## Required measurement intents

1. list scene objects and stable hierarchy paths;
2. read parent transforms and pivot locations;
3. measure declared dimensions and ratios;
4. list mesh material slots and resolved assignments;
5. measure per-mesh UV coverage;
6. count non-manifold edges and measure `V`, `E`, `F` or Euler characteristic;
7. capture declared reference views as PNG;
8. save the scene and report a host-owned artifact or scene digest.

## Host notes

- Maya: use scene, geometry/mesh, materials, UV, and render/viewport Skills.
  Interactive viewport capture must fail closed when no visible model panel exists;
  do not auto-show or mutate the UI to obtain evidence.
- Blender: use shared typed modeling, topology, material, UV, scene, and viewport
  tools. Prefer evaluated readback from Blender over operator acknowledgement.
- Houdini: measure the cooked geometry and material assignments at the declared
  output node. Keep SOP topology facts separate from object hierarchy facts.
- 3ds Max: measure node hierarchy, pivots, modifiers/evaluated mesh, material
  slots, and UV channels from typed adapter tools on the main thread.

## Missing capability

If a host cannot return one required fact, stop that gate and add the smallest
typed, read-only measurement to the owning adapter with real-host verification.
Do not substitute arbitrary Python, HScript/MAXScript/MEL execution, generic UI
automation, or an inferred screenshot result in this cross-DCC package.

# Controlled Modeling Vocabulary

Use these terms consistently in specs and review notes.

| Term | Meaning |
| --- | --- |
| part | One named functional or visual component with a stable spec id. |
| required part | A part that must exist at every stage that checks required parts. |
| silhouette | The outer contour from a declared view, independent of materials. |
| proportion | A dimensionless ratio between two named measurements. |
| tolerance | Maximum absolute deviation allowed for a declared proportion. |
| hierarchy | Parent-child transform ownership for declared parts. |
| pivot | Declared transform origin and rotation intent for one part. |
| material slot | A named binding point on a part or mesh. |
| UV coverage | Fraction of mesh faces with valid UV coordinates, from 0 to 1. |
| unbound slot | A material slot with no resolvable material assignment. |
| non-manifold edge | An edge whose face adjacency violates the declared surface topology. |
| Euler characteristic | Measured `V - E + F`, compared with the expected topology value. |
| NEVER constraint | A prohibited outcome that no correction may introduce. |
| blocking uncertainty | Missing information that prevents the relevant stage from starting. |
| stage gate | Declared measured checks that must pass before advancing. |
| correction | One bounded scene or spec change followed by remeasurement. |
| plateau | Two consecutive review cycles without measurable improvement. |
| oscillation | Alternation between previously observed outcomes. |
| comparison sheet | Reference and captures packaged together without scoring. |

Avoid subjective words such as “better,” “clean,” or “accurate” without naming
the observable part, view, measurement, or acceptance check that changed.

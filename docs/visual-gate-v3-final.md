# Visual Product Gate v3 — Final Contract

- `data-car-layer="primary"` is emitted by master and vertical scene generators.
- Technical visual families are explicit composites and retain the primary vehicle layer.
- `car_first_ratio` is measured from the explicit attribute and must be at least `0.70`.
- Contract suite contains CONTRACT_29, CONTRACT_30, and CONTRACT_31.
- CI runs a real `artifact_gate` before `production_render`.
- CI produces `qa_report.json`, a test master, a test Short, a production master, and four production Shorts.
- Each production Short receives a final Visual Product Gate pass with one render retry before being recorded in `failed_shorts`.
- Artifact retention is 7 days.

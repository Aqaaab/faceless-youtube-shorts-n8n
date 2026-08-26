# Faceless YouTube Production V3

Clean rebuild of the production pipeline.

## Architecture

`Repository Audit → Contracts → Provider Registry → Odysseus → Story → Render → 4 Shorts → QA → Artifact`

Odysseus is the only AI boundary used by production code. Future providers are extension points only and remain disabled until independently verified.

## Output contract

- 1 long-form video: 7–15 minutes
- exactly 4 Shorts
- production runs only when triggered/scheduled
- generated artifacts are retained for 7 days

## Checks

```bash
python -m unittest discover -s tests -v
python scripts/system_gate.py
```

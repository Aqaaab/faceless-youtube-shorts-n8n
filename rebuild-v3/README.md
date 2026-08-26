# Faceless YouTube Production V3

Clean production architecture centered on Odysseus as the only AI entry point.

## Pipeline

Repository audit → contracts → provider registry → Odysseus gateway → story → render → 4 Shorts → QA → artifact.

Odysseus is ephemeral: the production workflow starts it only for the generation job when a local image is configured. Remote Odysseus can also be supplied through `ODYSSEUS_BASE_URL` and `ODYSSEUS_API_KEY`.

Additional providers can be added later under `providers/` without changing the production workflow. Providers must be registered with capabilities and health policy before activation.

## Local checks

```bash
python -m unittest discover -s tests -v
python scripts/system_gate.py
```

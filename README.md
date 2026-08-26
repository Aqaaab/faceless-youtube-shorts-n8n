# Faceless YouTube Production v3

Clean rebuild of the production line. Odysseus is the only AI entry point for the production workflow. Optional provider adapters live behind a registry and can be added later without changing the pipeline contract.

## Pipeline

`Repository Gate → File/Import Gate → Provider Registry → Odysseus Gateway → Story → Fallback Providers → Render → 4 Shorts → QA → Artifact`

## Runtime

Odysseus is treated as an ephemeral dependency: the production workflow connects to an already reachable Odysseus endpoint only for the run. Provider API keys are never sent to Odysseus by this repository.

Required GitHub Actions secrets for a real run:

- `ODYSSEUS_GATEWAY_BASE_URL`
- `ODYSSEUS_GATEWAY_API_KEY`
- `PEXELS_API_KEY`
- YouTube OAuth secrets used by the uploader

Fallback providers are disabled unless explicitly enabled in `config/providers.json` and their corresponding secret exists.

# V3 Architecture

Odysseus is the single AI boundary. Production code never calls a model provider directly.

The upstream Odysseus project exposes browser chat at `/api/chat` and a scoped token surface at `/api/v1/chat`. This project keeps the boundary configurable; the current client uses `/api/chat` and does not invent a `/api/v1/chat` route.

Future providers live under `providers/<name>/` and are disabled by default. A provider can only be activated after capability declaration, configuration validation, and a live health check. Adding a provider must not require editing the production workflow.

Pipeline:

`Repository Audit → File/Import Contracts → Provider Registry → Odysseus → Story → Render → 4 Shorts → QA → Artifact`

Production contract:

- one long-form video between 7 and 15 minutes;
- exactly four Shorts;
- Odysseus is the primary AI boundary;
- provider credentials stay outside the repository;
- production is ephemeral and does not require a 24/7 runtime.

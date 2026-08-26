# Odysseus integration

Odysseus is the optional primary intelligence/agent layer. The repository does **not** vendor its source code or individual provider credentials.

## Architecture

```text
Odysseus
   -> OpenAI-compatible Aqaaab gateway
   -> Aqaaab AI Router
   -> free-only provider mesh
   -> production engines / QA
```

The gateway is intentionally disabled by default. This prevents an unconfigured Odysseus instance from becoming a production failure point.

## Official Odysseus deployment

Use the official repository and its Docker Compose deployment. The official setup guide recommends Docker Compose and exposes the UI on port 7000 by default.

Repository: https://github.com/odysseus-dev/odysseus
Setup: https://github.com/odysseus-dev/odysseus/blob/main/docs/setup.md

## Aqaaab gateway

Start the gateway on the same host as Odysseus:

```bash
export ODYSSEUS_GATEWAY_ENABLED=true
export ODYSSEUS_GATEWAY_HOST=127.0.0.1
export ODYSSEUS_GATEWAY_PORT=8787
python scripts/odysseus_gateway.py
```

The OpenAI-compatible endpoint is:

```text
http://127.0.0.1:8787/v1
```

Use model `aqaaab/story` for the production-proven long-story router. The other declared model names remain reserved until their dedicated task routers are wired; the gateway fails closed rather than silently using the wrong task router.

## Security

Do not put provider API keys into Odysseus. The gateway keeps the individual keys in the Aqaaab runtime and only returns the selected provider/model metadata. The production contract explicitly requires this separation.

## Production behavior

Odysseus is primary for intelligence when explicitly enabled. Aqaaab AI Router remains the fallback. Production still requires the existing fixed-slot, QA, artifact, and four-Shorts gates.

# Aqaaab AI Router

The repository now has a project-owned AI routing layer. It wraps the existing provider implementations instead of deleting or replacing them.

## Guarantees

- `free_only=true` and fail-closed behavior.
- Provider-specific cooldowns after auth, quota, access, model, or rate-limit failures.
- Conservative token estimation before a request.
- Per-run routing state and machine-readable routing ledger in `RUN_DIR/ai_router/`.
- Provider priority by task; long-form generation prefers high-capacity providers first.
- Existing OpenRouter, Gemini, Cloudflare, Groq, Together, QwenCloud, and Cerebras integrations remain available.

## Production integration

`patent_story_engine_router.py` is the safe integration point for the new router. The original `patent_story_engine.py` is intentionally retained unchanged while the new path is validated.

The validation workflow is:

`.github/workflows/ai-router-validation.yml`

It performs syntax checks, unit tests, free-only contract checks, provider inventory, and router construction without consuming provider quota.

## Routing state

The router writes:

- `ai_router/state.json`
- `ai_router/routing_ledger.json`

These files make provider decisions observable and make future persistent quota learning possible without changing the production contract.

## Important limitation

A provider's public `/models` endpoint is not proof of remaining inference quota. Real inference probes should only be enabled when their quota cost is acceptable. The router therefore fails closed on known `402/403/429` conditions and does not retry providers that are already classified as unavailable.

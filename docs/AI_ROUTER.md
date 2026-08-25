# Aqaaab AI Router

The repository has a project-owned, free-only AI routing layer for long-form story generation.

## Guarantees

- `free_only=true` and fail-closed behavior.
- Provider-specific classification and cooldowns for auth, quota, access, model, rate-limit, transient, and schema failures.
- Per-run routing state and a machine-readable routing ledger under `RUN_DIR/ai_router/`.
- Real inference health checks for the additional OpenAI-compatible provider pool.
- A provider registry audit that checks registry, adapter, workflow-secret, enable-flag, and routing-order consistency.
- Deterministic fallback remains disabled in production.

## Active provider architecture

The long-story route uses the project-owned providers first and the additional compatible providers as backups.

Core providers include QwenCloud, the free BlockRun NVIDIA pool, Groq, Gemini, Cerebras, Cohere, Together, OpenRouter, and Cloudflare.

The additional OpenAI-compatible backup pool contains nine providers:

`Mistral`, `SambaNova`, `HuggingFace`, `ZAI`, `LLM7`, `AnyAPI`, `ArliAI`, `OllamaCloud`, `ModelScope`.

A provider is eligible only when its key is passed by GitHub Actions, its `ENABLE_*_PROVIDER` flag is true, and its live health check succeeds.

## Production integration

The production story entrypoint is:

`scripts/patent_story_engine.py`

`scripts/patent_story_engine_router.py` is only a compatibility wrapper and is not the production path.

The main workflow is:

`.github/workflows/daily-production-v2.yml`

Validation is performed by:

`.github/workflows/ai-router-validation.yml`

## Routing state

The router writes:

- `ai_router/state.json`
- `ai_router/routing_ledger.json`

These files make provider decisions observable and support future quota learning without changing the production contract.

## Important limitation

A provider's `/models` response is not proof of entitlement or remaining quota. The additional-provider pool therefore performs a real small inference check before activation, while still keeping production fail-closed on known unavailable conditions.

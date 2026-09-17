# Zero-Cost Audit — Automotive Content Engine

**Hard rule:** runtime API/provider cost must be exactly `$0.00`. Paid APIs and paid model routing are prohibited.

| المصدر | الموقع في الكود | مجاني؟ | القرار |
|---|---|---:|---|
| Odysseus Gateway | `app/core.py`, `ODYSSEUS_GATEWAY_*` | ✅ | المسار الرئيسي والوحيد للـLLM |
| Gemini Flash | Odysseus upstream (`ODYSSEUS_UPSTREAM_*`) | ✅* | مسموح فقط ضمن Gemini Free Tier؛ لا paid tier أو paid grounding |
| Gateway free-only fallback | Odysseus health contract | ✅* | مسموح فقط عندما تكون `free_only=true` و`paid_models_allowed=false` و`cost_usd=0` |
| OpenRouter paid models | Gateway/provider policy | ❌ | محظور؛ لا paid fallback ولا paid API key |
| AISA / OpenAI / Anthropic / Claude / GPT / Cohere direct APIs | searched code/config | ❌/غير مطلوب | لا مسارات مباشرة؛ Odysseus فقط |
| YouTube Data API | `app/upload.py`, `YOUTUBE_*` | ✅ API quota | مسموح للنشر فقط؛ لا تكلفة API مباشرة |
| FFmpeg / Pillow / Edge TTS | runtime dependencies | ✅ | محلية/مفتوحة المصدر أو خدمة مجانية؛ لا paid API |

\* Free availability depends on the external provider account staying within its free allowance. A paid billing tier or paid model configuration violates this project's zero-cost policy and must fail the production preflight.

## Required invariants

- No direct external LLM provider route in application code.
- `ODYSSEUS_MAX_ATTEMPTS`: `3`.
- Gateway health must report a configured free-only route; production rejects paid models.
- `paid_services_used`: `[]`.
- Artifact `cost_usd`: `0.00`.
- Invalid model JSON: retry, never success.
- Failure after retries: raise; never switch to a paid/direct provider.

## Decision

The system deliberately fails closed. Provider outage, quota exhaustion, or a paid gateway configuration is a production failure, not a reason to spend money.

**Audit status:** enforced in source, CI, gateway health contract, and production preflight.

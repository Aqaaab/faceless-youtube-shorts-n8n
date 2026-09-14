# Zero-Cost Audit — Automotive Content Engine

**Hard rule:** runtime API/provider cost must be exactly `$0.00`. No paid API, no OpenRouter, no paid fallback.

| المصدر | الموقع في الكود | مجاني؟ | القرار |
|---|---|---:|---|
| Odysseus Gateway | `app/core.py`, `ODYSSEUS_GATEWAY_*` | ✅ | المسار الرئيسي والوحيد للـLLM |
| Gemini Flash | Odysseus upstream (`ODYSSEUS_UPSTREAM_*`) | ✅* | مسموح فقط ضمن Gemini Free Tier؛ لا paid tier أو grounding |
| OpenRouter | searched code/config | ❌ | محظور ومحذوف |
| AISA / OpenAI / Anthropic / Claude / GPT / Cohere direct APIs | searched code/config | ❌/غير مطلوب | لا مسارات مباشرة؛ Odysseus فقط |
| YouTube Data API | `app/upload.py`, `YOUTUBE_*` | ✅ API quota | مسموح للنشر فقط؛ لا تكلفة API مباشرة |
| FFmpeg / Pillow / Edge TTS | runtime dependencies | ✅ | محلية/مفتوحة المصدر أو خدمة مجانية؛ لا paid API |

\* Google documents a Free Tier for Gemini Flash with free input/output within its limits. The project permits Gemini only as the configured Odysseus upstream and does not configure paid-provider failover or paid grounding. If the upstream Google project is moved to a paid billing tier, that external account state violates this project's zero-cost policy and production must be stopped.

## Required invariants

- OpenRouter occurrences in executable/config source: `0`.
- `ODYSSEUS_MAX_ATTEMPTS`: `3`.
- Gateway fallback count: `0`.
- Gateway fallback list: `[]`.
- Paid services used: `[]`.
- Artifact `cost_usd`: `0.00`.
- Invalid model JSON: retry, never success.
- Failure after retries: raise; never switch provider.

## Decision

The system deliberately fails closed. A provider outage or quota exhaustion is a production failure, not a reason to spend money or switch to a paid provider.

**Audit status:** enforced in source, CI, gateway health contract, and production preflight.

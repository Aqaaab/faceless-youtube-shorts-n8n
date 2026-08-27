# Faceless YouTube Production

Resilient production line for one long YouTube video plus four Shorts per run.

## Architecture

`GitHub Actions → Odysseus Gateway → Story Engine → Long Video + 4 Shorts → QA → Artifact`

Odysseus is the **primary AI entry point**. If the primary gateway returns a retryable failure or transport failure, the YouTube runtime uses its configured fallback chain:

`Odysseus → YOUTUBE_LLM (optional) → Gemini`

Provider keys are never sent to Odysseus. Fallback selection and retries happen locally in the YouTube runtime so a degraded primary service does not destroy the production run.

## Production contract

- 1 long video per run
- 7–15 minutes (420–900 seconds)
- 25 story scenes
- 4 Shorts
- 28–59 seconds per Short
- 1080×1920 Shorts at 30 FPS
- 1920×1080 long video at 30 FPS
- Pexels media + Edge TTS + FFmpeg rendering
- Retry/backoff for gateway, Pexels and TTS operations
- Final media QA is mandatory before artifact upload

## Required GitHub Actions secrets

- `ODYSSEUS_GATEWAY_BASE_URL`
- `ODYSSEUS_GATEWAY_API_KEY`
- `PEXELS_API_KEY`
- `GEMINI_API_KEY` (recommended fallback)

Optional direct YouTube fallback:

- `YOUTUBE_LLM_BASE_URL`
- `YOUTUBE_LLM_API_KEY`
- `YOUTUBE_LLM_MODEL`

Optional:

- `GEMINI_MODEL` — defaults safely to `gemini-3.7-flash` when the secret is empty.

Existing YouTube OAuth credentials are intentionally not removed by this rebuild and can be used by a later upload stage.

## Reliability rules

- Retryable HTTP failures: `408, 429, 500, 502, 503, 504`.
- Primary failure does not expose provider credentials to Odysseus.
- Empty/invalid model secrets fall back to a known Gemini model.
- A failed primary smoke test is reported as degraded when a fallback is configured.
- Production still fails closed when no usable LLM provider exists.
- Final QA validates file existence, duration, resolution, frame rate, audio and provider provenance.

## Design rule

Do not add provider keys to GitHub workflow commands or send them to Odysseus. New model providers must be added as explicit fallback adapters with tests and contract validation.

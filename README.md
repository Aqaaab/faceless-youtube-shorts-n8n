# 🤖 Faceless YouTube Automation

Automated long-form YouTube production with a **7–15 minute source video plus four extracted Shorts**, using the Aqaaab AI Router, Kokoro TTS, Pexels, FFmpeg, Vision QA, and YouTube publishing.

## Current production architecture

```text
Trend discovery
      ↓
Idea Generation Council
      ↓
Aqaaab AI Router
      ↓
7–15 min English long-form story
      ↓
20 validated scenes / ~1050–2100 words
      ↓
Kokoro TTS + Pexels + Arabic subtitles + music + animation
      ↓
1920×1080 long-form video
      ↓
Visual QA + Feature QA + Technical QA
      ↓
Viral scene selection
      ↓
Exactly 4 distinct Shorts
      ↓
1080×1920 vertical extraction
      ↓
YouTube publishing: 1 long video + 4 Shorts
```

The main production workflow is `.github/workflows/daily-production-v2.yml`. It builds the trend/council plan, generates the long story, renders the long-form source, performs QA, selects four distinct Shorts, and packages the final production artifact.

A separate `publish-production.yml` workflow is triggered only after the production workflow completes successfully. It downloads the approved artifact from that exact run and publishes the long video and all four Shorts through the YouTube Data API.

## Long-form contract

The long-form story is not a Short and must never use the Short's 80–110-word contract.

Production requirements:

- Duration: **7–15 minutes**, measured on the final MP4.
- English narration: **1050–2100 words**.
- Default scene count: **20**; allowed range 18–30.
- Scene narration: 45–70 English words.
- English narration is spoken; Arabic is rendered as subtitles.
- Long-form resolution: **1920×1080, H.264/AAC, 30 fps**.
- AI deterministic/baseline fallback is prohibited.

`scripts/patent_story_engine.py` is the production long-story generator and uses the long-story AI Router task. `scripts/router_long_story.py` is the standalone strict-validation generator used by the long-form validation workflow.

## Four-Short contract

Four Shorts are extracted from the finished long-form video rather than generated as unrelated stories.

- Exactly **4** Shorts per long video.
- Distinct source scene starts.
- Target duration: **15–60 seconds** each.
- Resolution: **1080×1920, H.264/AAC, 30 fps**.
- Selection uses `scripts/viral_engine.py` and `scripts/content_intelligence_upgrade.py`.
- Rendering uses `scripts/short_factory.py`, which crops the 16:9 source into a true 9:16 frame.

## AI Router

The Aqaaab AI Router is free-only and validation-aware. It tracks provider health, cooldowns, schema failures, and routing decisions. Long-form generation uses `build_long_story_router()` and preserves the provider/model metadata in the generated story.

`router_short_story.py` is no longer part of the production path. The active long-form path uses `patent_story_engine.py` for production and `router_long_story.py` for strict render validation.

## Rendering

`scripts/produce.sh` is format-aware:

- `format=patent` / `long_form` → 1920×1080, 7–15 minute validation, 18–30 scenes, 45–70 words per scene.
- Short format → 1080×1920, 28–45 second validation, 5–10 scenes, 8–18 words per scene.

The renderer creates English Kokoro narration, portrait stock footage, animated scene motion, Arabic ASS subtitles, optional background music, and the final MP4. The final contract records format, duration, resolution, AI provider, music, animation, voice, and subtitles.

## QA gates

The long-form pipeline must pass:

1. AI Router/provider contract.
2. Long-story schema and word-count validation.
3. Pexels/content preflight.
4. Render contract.
5. Visual QA.
6. Final Feature QA.
7. Final duration/resolution/codec validation.
8. Four-Short diversity and format validation.
9. Publication contract before YouTube upload.

## GitHub Actions

- `.github/workflows/daily-production-v2.yml` — production pipeline.
- `.github/workflows/strict-longform-validation.yml` — strict 7–15 minute render validation on `main` pushes or manual dispatch.
- `.github/workflows/publish-production.yml` — automatic publishing after a successful production run.

Required publishing secrets:

```text
YOUTUBE_CLIENT_ID
YOUTUBE_CLIENT_SECRET
YOUTUBE_REFRESH_TOKEN
```

Required media/AI secrets depend on the selected providers and production path, including `PEXELS_API_KEY` and the configured free AI provider credentials.

## Local n8n deployment

The repository also contains a self-hosted n8n stack for optional development and integration:

```bash
cp .env.example .env
docker compose up -d --build
```

The Docker image includes n8n, FFmpeg, Python, Kokoro TTS, fonts, and the media scripts.

## Important notes

A successful workflow run means the configured services were available and the generated media passed the repository's contracts for that run. It does not guarantee uninterrupted availability of third-party providers.

For automated publishing, keep the channel and generated content compliant with YouTube policies and review the first production runs while tuning the system.

## License

MIT

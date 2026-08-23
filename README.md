# 🤖 Faceless YouTube Shorts Automation

Automated YouTube Shorts production with **Gemini + Kokoro TTS + Pexels + FFmpeg + YouTube Data API**, with an optional self-hosted n8n deployment.

## Current production pipeline

The primary production path is the GitHub Actions workflow:

```text
Schedule / manual run
        ↓
Gemini 3.6 Flash
        ↓
Validated 5-scene English + Arabic job.json
        ↓
Kokoro TTS — af_bella
        ↓
Pexels portrait footage per scene
        ↓
FFmpeg scene rendering + Arabic/English ASS subtitles
        ↓
Optional background music
        ↓
Final 1080×1920 H.264/AAC Short
        ↓
YouTube upload
```

The workflow is designed to stop early when a required secret, model response, audio file, video file, or final media property is invalid. The final validation requires **30–60 seconds, 1080×1920, 30 fps, and AAC audio**.

## GitHub Actions

Workflow: `.github/workflows/youtube-shorts.yml`

Required repository Secrets:

```text
GEMINI_API_KEY
PEXELS_API_KEY
YOUTUBE_CLIENT_ID
YOUTUBE_CLIENT_SECRET
YOUTUBE_REFRESH_TOKEN
```

The workflow uses `gemini-3.6-flash` by default, with retry handling for transient API failures. It downloads the Kokoro model and voices during the run and performs a real TTS smoke test before production.

The YouTube upload defaults to `private` through `YOUTUBE_PRIVACY_STATUS`. Keep this while testing the pipeline.

## Renderer

`scripts/produce.sh` is the main media engine. It expects:

```text
<RUN_DIR>/job.json
```

A valid job contains five scenes with:

```text
text_en
text_ar
pexels_query
```

The renderer generates per-scene Kokoro narration, sources portrait stock footage, renders animated vertical scenes, creates bilingual ASS subtitles, optionally mixes background music, concatenates the scenes, and validates the final MP4.

`scripts/produce_satisfying.sh` is a separate no-narration transformation engine for cleaning/construction-style Shorts. It is not part of the primary Gemini/Kokoro workflow but is kept compatible with the repository's optional n8n workflows.

## Local n8n deployment

The repository also contains a self-hosted n8n stack:

```bash
cp .env.example .env
docker compose up -d --build
```

Then open `http://localhost:5678` and import the workflow JSON from `workflows/`.

The Docker image includes n8n, FFmpeg, Python, Kokoro TTS, fonts, and the media scripts. `docker-compose.yml` mounts `/data`, `/assets`, `/scripts`, and `/workflows` so the renderer can be developed without rebuilding for every script change.

The legacy n8n builder files may still use Groq for their n8n-specific workflows; the GitHub Actions production path does **not** depend on Groq.

## Repository layout

```text
.
├── .github/workflows/youtube-shorts.yml   # primary production workflow
├── Dockerfile                              # local n8n + media image
├── docker-compose.yml                      # local n8n stack
├── scripts/
│   ├── generate_job.py                     # Gemini job generator/validator
│   ├── produce.sh                          # primary Shorts renderer
│   ├── produce_satisfying.sh               # optional satisfying renderer
│   └── upload_youtube.py                   # YouTube OAuth upload
├── workflows/                              # importable n8n workflows
├── assets/                                 # optional local music/fonts
└── data/                                   # runtime output; normally gitignored
```

## Testing

Before a production run, the workflow automatically validates:

```bash
bash -n scripts/*.sh
python -m py_compile scripts/*.py
node --check build_workflow.js
node --check build_cleaning_workflow.js
```

It also performs a real Kokoro TTS test, validates `job.json`, validates the final media, and stores the run output as a GitHub Actions artifact.

## Important notes

API quotas and third-party service availability can change. A successful pipeline run therefore means that the configured services were available and the generated video passed the repository's media checks for that specific run; it does not guarantee uninterrupted service availability.

For automated publishing, keep the channel and content compliant with YouTube policies and review generated content while tuning the system.

## License

MIT

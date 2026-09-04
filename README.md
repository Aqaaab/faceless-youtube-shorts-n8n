# Faceless YouTube Car Encyclopedia

Canonical production line for one automotive encyclopedia master video plus four Shorts derived directly from that master.

## Canonical architecture

`GitHub Actions → Topic Selector → Odysseus Gateway → Story Engine → Strict Story Gate → Automotive Gate → Episode Blueprint → 25-scene Master Render → Technical HUD → Caption Hardening → QA → Episode Quality Gate → YouTube Publish → Artifact`

The project is permanently locked to the **cars / automotive technology** niche. Legacy historical-story and standalone-Short production paths have been removed from the production surface.

## Episode contract

- 1 master long-form video per run
- 7–15 minutes (420–900 seconds)
- exactly 25 scenes
- English narration with publication-quality Modern Standard Arabic subtitles
- automotive identity, generation/year and exact trim/engine specificity when available
- component-level explanation: what it is, where it is, when it operates, how it works, why it matters and failure symptoms when relevant
- technical explanations for engine, turbo/airflow, fuel, cooling, transmission, drivetrain, brakes and suspension where relevant to the vehicle
- power, torque, acceleration and top-speed claims are source-controlled when stated numerically
- modification sections distinguish stock facts from estimated modified outcomes and include supporting cooling/fuel/brake/drivetrain requirements
- technical information is reinforced with locally generated HUD/flow annotations; Pexels is the only external footage source

## Shorts contract

- exactly 4 Shorts per master
- 28–59 seconds each
- 1080×1920 at 30 FPS
- every Short maps to exactly one unique master scene
- no independent Short narration generation
- four editorial roles: vehicle hook, technical explainer, performance/upgrade, competitive edge

## Reliability and safety gates

The workflow fails closed when the contract is broken. Gates cover scene count, automotive-only content, duplicate Pexels queries, Short-to-master mapping, trusted-source mapping for numeric vehicle specifications, legacy-content detection, media duration and file integrity.

Technical modification numbers are treated as estimates, never guarantees. The project avoids presenting unsupported vehicle-specific specifications as facts.

## AI routing

Odysseus is the primary AI entry point. On retryable or transport failure, the YouTube runtime can use its configured fallback chain:

`Odysseus → YOUTUBE_LLM (optional) → Gemini`

Provider keys stay in the YouTube runtime and are never sent to Odysseus.

## Required GitHub Actions secrets

- `ODYSSEUS_GATEWAY_BASE_URL`
- `ODYSSEUS_GATEWAY_API_KEY`
- `PEXELS_API_KEY`
- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

At least one usable LLM route is also required:

- `GEMINI_API_KEY`, or
- `YOUTUBE_LLM_BASE_URL` + `YOUTUBE_LLM_API_KEY`

Optional model configuration:

- `GEMINI_MODEL` — defaults to `gemini-3.7-flash`
- `YOUTUBE_LLM_MODEL`

## Canonical workflow

Use `.github/workflows/daily-production.yml`. It supports manual `workflow_dispatch` and the scheduled daily run. The removed `odysseus-integration.yml` workflow is intentionally no longer part of production to prevent duplicate generation/upload paths.

## Output

The run produces the master video, four derived Shorts, captions, episode blueprint, source register, render manifest and QA reports. The master remains the single source of truth for the episode.

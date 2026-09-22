# Automotive AI Content Engine

Production-oriented Arabic automotive YouTube engine.

## Outputs
- 1 connected long-form video: 7–15 minutes, exactly 25 scenes, native 1920×1080.
- 4 native Shorts: 1080×1920, 28–59 seconds.
- Burned Arabic subtitles with synchronized scene timing.
- Automated technical + visual product gates before publishing.
- Optional YouTube upload only after the complete production gate passes.

## Rendering architecture

GitHub Actions → Odysseus Gateway → Story Engine → **Blender/EEVEE automotive renderer** → FFmpeg assembly → Arabic subtitle burn → technical QA → visual product QA → YouTube.

The production vehicle renderer is Blender/EEVEE. The current asset is a deterministic procedural 3D automotive baseline with physically rendered materials, wheels, glazing, lighting, reflections and multiple camera families. It is intentionally provider-free and requires no image-generation API key.

Pillow remains available for image QA and legacy utilities; it is not the production vehicle renderer.

## Quality contract

A green unit/CI check alone is not considered product success. Production requires:
- 25 valid connected scenes.
- Master duration 420–900 seconds.
- Four Shorts at 28–59 seconds and 1080×1920.
- Native portrait composition without black/empty delivery bands.
- Car-first visual composition and meaningful camera diversity.
- Blender-rendered raster evidence for the vehicle frames.
- Arabic subtitle evidence and synchronization.
- No stock-media dependency.
- No paid-provider route.
- Publishing blocked when mandatory gates fail.

The minimum release target for the current hardening pass is **87/100 product readiness before CI/archive acceptance**; the engineering target remains 10/10.

## Required secrets

`ODYSSEUS_GATEWAY_BASE_URL`, `ODYSSEUS_GATEWAY_API_KEY`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`, `YOUTUBE_PRIVACY_STATUS`.

Publishing remains manual/explicit after rebuild and only occurs after all mandatory QA gates pass.

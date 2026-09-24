# Faceless YouTube Shorts — n8n

This repository is an automated automotive content engine.

## Production architecture

The production renderer is **Blender + EEVEE**. The vehicle is generated as a procedural 3D automotive asset and rendered to raster frames before video assembly.

Production contract:
- 25 connected master scenes.
- Master duration 420–900 seconds.
- Four Shorts at 28–59 seconds each, 1080×1920.
- Native portrait composition without black/empty delivery bands.
- Car-first visual composition and meaningful camera diversity.
- Blender-rendered raster evidence for the vehicle frames.
- Curved-profile automotive body geometry with dedicated wheel, glass, lighting and material detail.
- Arabic subtitle evidence and synchronization.
- No stock-media dependency.
- No paid-provider route.
- Publishing blocked when mandatory gates fail.

The minimum release target for the current hardening pass is **87/100 product readiness before CI/archive acceptance**; the engineering target remains 10/10.

## Required secrets

`ODYSSEUS_GATEWAY_BASE_URL`, `ODYSSEUS_GATEWAY_API_KEY`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`, `YOUTUBE_PRIVACY_STATUS`.

Publishing remains manual/explicit after rebuild and only occurs after all mandatory QA gates pass.

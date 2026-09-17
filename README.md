# Automotive AI Content Engine

Automotive AI production engine for one topic: **1 long-form video (7–15 minutes, exactly 25 connected scenes) + 4 native Shorts (28–59 seconds, 1080×1920)**. Arabic subtitles are burned into the final MP4 files.

## Production contract

The visual product is automotive-editorial first: the car remains the primary subject, while camera family, component detail, semantic mode, motion, and information layout must vary across the 25 scenes. Shorts are authored natively for 9:16 rather than being simple crops. Subtitle rendering uses outline-only Arabic text with short timed cues and safe margins; oversized subtitle panels, replacement glyphs, debug/internal text, and edge clipping are hard failures.

The final product gate is **Visual Product Gate v4**. It requires all 25 scene assets, 25/25 car-primary coverage, high rendered-asset uniqueness, at least 10 visual families, 10 camera families, 5 semantic modes, 5 motion types, and verified subtitle evidence for the master and all four Shorts. Final QA requires a passing v4 gate at ≥90/100 and a weighted product score of ≥9/10 before publishing.

## Architecture

GitHub Actions → Odysseus Gateway → Story Engine → Automotive Visual Scene Design → Edge TTS → Timed Arabic Subtitles → FFmpeg → Final QA/Product Gate → YouTube.

No external stock-media fallback is part of the production path. AI access is routed through Odysseus; the production workflow rejects paid-provider source references and requires a zero-cost gateway contract.

## Required GitHub Actions secrets

`ODYSSEUS_GATEWAY_BASE_URL`, `ODYSSEUS_GATEWAY_API_KEY`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`, `YOUTUBE_PRIVACY_STATUS`.

For YouTube upload **and rerun deduplication**, the OAuth refresh token must be created with both scopes:

`https://www.googleapis.com/auth/youtube.upload`

`https://www.googleapis.com/auth/youtube.readonly`

The OAuth flow must use offline access so GitHub Actions can refresh the access token without an interactive sign-in. Never commit or paste the refresh token into source control or chat.

## Publishing gate

Publishing is blocked unless the final artifact, four Shorts, QA report, subtitle evidence, hashes, and the strict Visual Product Gate v4 all pass. `YOUTUBE_PRIVACY_STATUS` accepts `public`, `private`, or `unlisted`. Reruns use content fingerprints plus an upload marker to avoid duplicate uploads.

The production workflow is manual by design. A refreshed YouTube token is required after an OAuth `invalid_grant`/revoked-token failure; rerunning with the same expired token is expected to fail again.

# Automotive AI Content Engine

Production-grade automotive editorial engine with a reusable Blender vehicle, dedicated cockpit, native portrait compositions, grounded callouts, and fail-closed product QA.

Outputs: 1 long-form video (7-15 minutes, exactly 25 scenes) and 4 native 1080x1920 Shorts (28-59 seconds). Arabic subtitles are burned into final MP4 files. Edge TTS and FFmpeg provide audio and rendering.

Architecture: GitHub Actions -> Odysseus Gateway -> Story Engine -> Blender Automotive Model -> Callout Overlay -> Edge TTS -> Subtitles -> FFmpeg -> Product QA -> YouTube.

Required secrets: ODYSSEUS_GATEWAY_BASE_URL, ODYSSEUS_GATEWAY_API_KEY, YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN, YOUTUBE_PRIVACY_STATUS.

Production is manual after rebuild; publishing occurs only after all QA gates pass.

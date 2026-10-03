# Automotive AI Content Engine

Production pipeline for premium Arabic automotive videos using a single WanGP visual-generation path, grounded Story/TTS data, deterministic assembly, product QA, and gated YouTube publishing.

Outputs: 1 long-form video (7-15 minutes, exactly 25 scenes) and 4 native 1080x1920 Shorts (28-59 seconds). Arabic subtitles are burned into final MP4 files. Edge TTS and FFmpeg provide audio/assembly.

Architecture: GitHub Actions -> Odysseus Gateway -> Story Engine -> WanGP reference + video generation -> Dynamic Short Selection -> Edge TTS -> FFmpeg assembly/subtitles -> Product QA -> gated YouTube publishing.

Required secrets: ODYSSEUS_GATEWAY_BASE_URL, ODYSSEUS_GATEWAY_API_KEY, WANGP_MCP_URL, WANGP_MCP_TOKEN, WANGP_VIDEO_MODEL_TYPE (optional), WANGP_REFERENCE_MODEL_TYPE (optional), WANGP_REFERENCE_MEDIA_ID (optional), YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN, YOUTUBE_PRIVACY_STATUS.

WanGP is fail-closed: missing MCP connectivity or an incompatible model is a production failure. No visual-provider fallback is allowed. Runtime media spend is $0 and Pexels/stock media are not used.

Production publishing runs only after every product gate and checksum verification passes.

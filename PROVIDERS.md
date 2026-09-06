# PROVIDERS.md

This file lists the external providers used by the project and how to use their free tiers when available.

- YouTube (Google APIs)
  - Free tier: Requires OAuth credentials; API usage is billed for some operations (e.g. certain quota limits). Create a project on Google Cloud and enable the YouTube Data API v3. Use OAuth client credentials (web application) and a refresh token.
  - How to start free: https://console.cloud.google.com/ (create a project, enable YouTube Data API). There may be a free quota; check the API quotas page. Use careful testing to avoid accidental uploads.

- Pexels
  - Free tier: Pexels provides a free API key for non-commercial use with rate limits. Sign up at https://www.pexels.com/api/ and request an API key.
  - How to start free: Use the key in PEXELS_API_KEY environment variable.

- Gemini (Google)
  - Some limited free access may be available via Google Cloud; otherwise billed.

- Edge TTS (edge-tts Python)
  - Free to use as a client library that calls Microsoft Edge voices (offline/local), but some voices may require online services. Check edge-tts docs.

- Google Auth / oauth libraries
  - Public libraries used for OAuth handling.

- ffmpeg / ffprobe
  - Open-source CLI tools; install via apt on Linux. No API keys.

- (Notes)
  - For local development, use mocked values or local test keys where possible.
  - Do not commit any real API keys to the repo.

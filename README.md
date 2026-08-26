# Faceless YouTube Production

Clean selective rebuild of the production line inside the existing repository.

## Architecture

`GitHub Actions → Odysseus Gateway → Story Engine → Long Video + 4 Shorts → QA → Artifact`

Odysseus is the **only AI entry point** used by this repository. Model/provider selection, retries and provider failover belong behind the Odysseus service boundary. This repository does not carry a direct provider registry or direct provider fallback path.

## Production contract

- 1 long video per run
- 7–15 minutes (420–900 seconds)
- 25 story scenes
- 4 Shorts
- 28–59 seconds per Short
- 1080×1920 Shorts
- Pexels media + Edge TTS + FFmpeg rendering
- Final QA is mandatory before artifact upload

## Required GitHub Actions secrets

For a real production run:

- `ODYSSEUS_GATEWAY_BASE_URL`
- `ODYSSEUS_GATEWAY_API_KEY`
- `PEXELS_API_KEY`

Existing YouTube OAuth credentials are intentionally not removed by this rebuild and can be used by a later upload stage.

## Design rule

Do not add direct model-provider calls to the GitHub workflow. If a new model/provider is needed, integrate it behind Odysseus without changing the production contract.

# Provider Evaluation — Automotive Content Engine

This registry is the decision record for integrations. A project is not added to the critical path merely because it is popular.

| Capability | Candidate | License / current GitHub scale | Free / API | GPU | Actions | Decision |
|---|---|---|---|---|---|---|
| Validation/contracts | Pydantic (`pydantic/pydantic`) | MIT; ~28.7k stars | Free / local | No | Yes | **Core**: strict Python domain validation; mature and supports modern Python.
| TTS | Kokoro (`hexgrad/kokoro`) | Apache-2.0; ~8.7k stars | Free / local | Optional | Yes, CPU path must be tested | **Preferred local**: strong quality/size tradeoff; model/dependency footprint must be measured in CI.
| TTS fallback | edge-tts (`rany2/edge-tts`) | MIT | Free / network | No | Yes | **Fallback**: lightweight network TTS already proven in the repository; not treated as fully offline.
| Speech alignment | faster-whisper (`SYSTRAN/faster-whisper`) | MIT; ~24.6k stars | Free / local | Optional | Yes | **Optional QA/alignment**: efficient transcription; keep out of the critical path until runtime cost is measured.
| Rendering | FFmpeg (`FFmpeg/FFmpeg`) | LGPL 2.1+ core; ~64k stars | Free / local | No | Yes | **Core**: canonical renderer and ffprobe validation.
| Programmatic video | Remotion (`remotion-dev/remotion`) | Special license; ~58.6k stars | Conditional free | No | Yes | **Optional**: powerful, but license makes it unsuitable as an unconditional core dependency.
| Media acquisition | Pexels API | Pexels API terms | Free API with limits | No | Yes | **Core external media source**; relevance scoring remains our code.
| Media download fallback | yt-dlp (`yt-dlp/yt-dlp`) | Unlicense source | Free / CLI | No | Yes | **Not primary**: useful only for permitted sources; downloaded-media rights remain separate.
| LLM routing | LiteLLM (`BerriAI/litellm`) | MIT outside enterprise; ~57.5k stars | Open source / many APIs | No | Yes | **Optional**: useful gateway, but engine interfaces remain independent.
| Local LLM | Ollama (`ollama/ollama`) | MIT | Free / local | Optional | Yes | **Optional**: local fallback where runner resources permit.

## Selection rules

1. Core path must work without a paid API.
2. Network APIs are wrapped by adapters and mocked in tests.
3. GPU is never required by the production contract.
4. Licenses are checked before shipping an integration, especially for commercial use.
5. Provider versions are pinned after an end-to-end compatibility test.
6. Provider failure must be observable and must not silently degrade fact integrity or visual correctness.

## Research notes

- FFmpeg is the baseline renderer: its GitHub mirror reports roughly 64k stars and an LGPL-first licensing model, with GPL components optional.
- Remotion is technically strong but its current license is conditional: individuals and small companies up to three employees can use it free, while larger for-profit entities need a company license. It therefore remains optional.
- Kokoro currently reports about 8.7k stars and Apache-2.0 licensing. Its repository documents CPU and optional GPU execution paths, making it a candidate for the TTS abstraction rather than a hard dependency.
- faster-whisper reports about 24.6k stars, MIT licensing, and a CTranslate2 implementation designed for lower memory/faster inference than the reference Whisper implementation.
- Pydantic is MIT-licensed and reports about 28.7k stars; it is suitable for the strict blueprint contract.
- yt-dlp is Unlicense-licensed at the source-repository level, but downloaded media remains subject to the source's copyright/licensing terms, so it is not a default media source.
- JSON Schema is the standards layer for machine-readable contracts and structural validation.

## Status

Phase 1 records candidates and establishes interfaces. No optional provider is promoted to the critical production path until its adapter, license, runtime footprint, and failure behavior are tested.

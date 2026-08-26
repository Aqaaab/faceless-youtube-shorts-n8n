# V3 Architecture

Odysseus is the single AI boundary. The production code never calls Gemini, Groq, Qwen, Cerebras, OpenRouter, or another provider directly.

Provider extension point:

`providers/<name>/adapter.py` + registration in `config/providers.json`.

Only providers with `enabled: true`, `healthy: true`, and required capabilities may be selected by a future router. The current production path uses Odysseus only.

Production contract: one long-form video (7–15 minutes) and exactly four Shorts.

# Zero-Cost Audit — Automotive Content Engine

**Hard rule:** runtime provider/API spend must be exactly **$0.00**. Only configured free-tier or locally hosted components are permitted.

| Component | Role | Cost policy |
|---|---|---|
| Odysseus Gateway | Story generation | Free-only route; fail closed on quota/error |
| WanGP | Image/video generation | Self-hosted/open-source runtime; no external paid generation API |
| YouTube Data API | Publishing | API quota only; no paid media service |
| FFmpeg / Pillow | Assembly/QA | Local/open-source |
| Edge TTS | Arabic voice generation | Free service path used by the pipeline |

## Production invariants

- paid_services_used must be [].
- cost_usd must be 0.0.
- Provider fallback is not permitted.
- WanGP must be the sole visual-generation engine.
- Missing WanGP connectivity is a production failure.
- Old renderer files, cache namespaces and gate identifiers are forbidden.
- Artifact QA must pass before publishing.

The production workflow does not rewrite the cost fields after QA. They are emitted by the application evidence itself.

**Audit status:** enforced by source consistency tests, CI, production preflight, visual gates and upload gates.

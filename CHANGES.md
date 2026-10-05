# CHANGES.md

## 2026-10-05 — Refactor / stabilization

### Step 1 — Baseline
- Baseline pinned to `main` commit `c270248805a50b390d85e1a83bf5fb979046e279`.
- Latest CI run: #777 (run `37253478913`).
- Compile/runtime prechecks passed.
- Full contract suite: **65 passed, 1 failed**.
- Failure: `tests/test_subtitle_style_contract.py::test_arabic_subtitles_use_outline_not_opaque_boxes`.
- Root cause: `app/render.py` is now a compatibility facade, but the contract test still requires the literal marker `FontName={family}` in that facade.
- No production behavior was changed in Step 1.
- Artifact, temporal smoke, and production-render jobs were not reached because the tests job failed.

### Existing refactor record
- `app/core.py` is a compatibility facade; Story generation, parsing, repair, gateway, and persistence live under `app/story/`.
- `app/render.py` is a compatibility facade; the active production renderer lives in `app/rendering.py`.
- Runtime defaults are centralized in `config/settings.py` and documented in `config/.env.example`.
- The temporary one-shot production workflow is absent from the current `main` tree.
- Pexels and the old persistent Blender renderer identifier are absent from the current `main` source search.

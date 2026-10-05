# CHANGES.md

## 2026-10-05 — Refactor / stabilization

### Step 1
- Reconciled the stale renderer contract test with the active Blender temporal renderer identifier.
- Reconciled vertical visual metadata with the actual renderer metadata instead of a legacy hard-coded persistent label.
- No production render algorithm, QA threshold, short selection, TTS, or YouTube behavior was intentionally changed.

### Baseline failure recorded
- CI run #751 failed 1 contract test.
- Root cause: the test expected `blender_eevee_automotive_v5_persistent`, while the active renderer is `blender_eevee_automotive_v5_temporal`.

## 2026-10-05 — Refactor continuation

### Completed
- `app/core.py` is now a compatibility facade; Story generation, parsing, repair, gateway, and persistence live under `app/story/`.
- `app/render.py` is now a compatibility facade; the active production renderer lives in `app/rendering.py` with one implementation of each render entrypoint.
- Runtime defaults are centralized in `config/settings.py` and documented in `config/.env.example`.
- Removed the temporary one-shot production workflow to avoid an extra push-triggered execution path.
- Removed duplicated artifact existence assertions from the production workflow.

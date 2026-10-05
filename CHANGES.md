# CHANGES.md

## 2026-10-05 — Refactor / stabilization

### Step 1
- Reconciled the stale renderer contract test with the active Blender temporal renderer identifier.
- Reconciled vertical visual metadata with the actual renderer metadata instead of a legacy hard-coded persistent label.
- No production render algorithm, QA threshold, short selection, TTS, or YouTube behavior was intentionally changed.

### Baseline failure recorded
- CI run #751 failed 1 contract test.
- Root cause: the test expected `blender_eevee_automotive_v5_persistent`, while the active renderer is `blender_eevee_automotive_v5_temporal`.

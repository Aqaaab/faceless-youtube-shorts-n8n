# Automotive Content Engine Architecture

This repository is being rebuilt around a provider-agnostic, stage-oriented automotive production engine. Existing `scripts/` code is treated as legacy until each capability is replaced and verified by the new engine; it is not part of the new public architecture.

## Pipeline

`Input → Research → Fact Validation → Story → Episode Blueprint → Scene Planner → Visual Engineering → Media → TTS → Subtitles → FFmpeg → Shorts → QA → Artifact Pack → Production`

## Boundaries

- `engine/models.py`: strict domain contracts.
- `engine/components/`: automotive component registry and visual constraints.
- `engine/providers/`: capability interfaces and provider selection/fallback.
- `engine/produce.py`: stable CLI entry point.
- `schemas/`: machine-readable contracts for CI and tooling.
- `tests_engine/`: focused tests for the new architecture.

## Design rules

1. Providers are adapters, never embedded in business logic.
2. Free/open-source paths are preferred; paid/credit providers remain optional.
3. Facts are source-backed and cannot be promoted to narration without validation.
4. Known automotive components must resolve through the registry before technical visuals are generated.
5. Unknown components are explicit QA warnings/errors, never silent generic HUD substitutions.
6. The final production gate is fail-closed.
7. FFmpeg remains the baseline renderer because it is lightweight, Linux-native, and suitable for GitHub Actions.

## Migration policy

The old production surface is not considered authoritative. During migration, new modules are added under `engine/`; old scripts may be removed once their replacement has passed equivalent tests and end-to-end validation. No legacy behavior is preserved solely for compatibility.

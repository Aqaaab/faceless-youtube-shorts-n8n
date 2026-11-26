# Automotive AI Content Engine audit — 2026-11-26

## State
**Not production-ready: contract tests pass, but visual artifact gate fails; production render is skipped.** Remediation is proposed on `fix/audit-2026-11-26`.

## Verified evidence

- Repository: `Aqaaab/faceless-youtube-shorts-n8n`, default branch `main`.
- Current main commit: `6d2b0150640b2b9d72eb31a69387cee4933e9152` (2026-10-18).
- Main CI run [39177514655](https://github.com/Aqaaab/faceless-youtube-shorts-n8n/actions/runs/39177514655):
  - `tests`: success.
  - `temporal_smoke`: success.
  - `artifact_gate`: failure.
  - `production_render`: skipped because the artifact gate failed.
- Exact failure in artifact gate: `camera pixel diversity failed: minimum cross-camera distance 0.0901 < 0.1000 (rear_long_lens vs road_follow)`.
- A later rebuild branch run [39493147662](https://github.com/Aqaaab/faceless-youtube-shorts-n8n/actions/runs/39493147662) repeated the same pair failure at `0.0843 < 0.1000`. Its tests and temporal smoke passed; artifact gate failed; production render skipped.
- The artifact upload step on the default CI workflow did not run after gate failure, and both failed runs returned no artifacts. The proposed branch changes upload partial evidence with `always()`.
- README describes a 7–15 minute long video with exactly 25 scenes, four native 1080x1920 Shorts of 28–59 seconds, Arabic subtitles, Blender, Edge TTS, FFmpeg and final QA. This is the intended contract, not proof that the latest production video was delivered.
- `.github/workflows/production.yml` is manual via `workflow_dispatch` or a push whose commit message contains `[launch-production]`. It has no scheduled trigger. YouTube publishing requires `inputs.publish == true`; the default is false.
- The production workflow requires Odysseus gateway and YouTube OAuth secrets. It performs a live Odysseus health preflight and asserts the declared zero-cost contract.
- The final uploader refuses to proceed unless master + four Shorts + QA reports + subtitle/visual/font evidence + manifest are present and pass provenance/hash checks.
- No production render artifact from the latest main CI run was available for visual inspection; production_render was skipped.

## Defects and gaps

1. **High — repeatable camera diversity failure:** `road_follow` and `rear_long_lens` produce near-identical pixel evidence under the strict camera gate in two separate runs. Metadata labels alone do not prove visual diversity.
2. **High — no daily autonomous production:** production is manual or commit-message-triggered; there is no `schedule` trigger.
3. **High — production publish remains opt-in:** the `publish` input defaults false. This is safe; enabling unattended public publishing requires explicit owner authorization and verified channel credentials.
4. **High — no visual artifact retention on failed gate:** prior CI failed before artifact upload, leaving no frame/video evidence for diagnosis. Proposed branch fixes this.
5. **High — uploader idempotency used title hash:** same media with a changed title could be uploaded again; same title with changed media could be treated as a duplicate. Proposed branch changes marker to media SHA-256 and scans the channel uploads playlist rather than the search endpoint's limited result set.
6. **High — realism is not objectively certified:** pixel distance, image metrics and rule-based gates can measure diversity/format, not human-level automotive realism, correct vehicle anatomy, motion quality, or factual correctness. Production visual review remains required.
7. **Medium — no external failure alerting:** current evidence is in GitHub Actions; no verified alert route or runbook was found in the inspected workflow.
8. **Medium — external TTS reliability:** Edge TTS is a free external dependency without a production SLA; transient failures and rate limits must be retried and surfaced.
9. **Medium — dependency ranges are not a fully locked environment:** requirements use version ranges rather than a fully reproducible lock.
10. **Medium — production workflow concurrency cancels an in-progress run:** `cancel-in-progress: true` can interrupt a long render if another run starts.
11. **Medium — no daily run budget/cost envelope:** zero-cost checks exist, but GitHub Actions minutes, cache use, and model request counts are not reported as a consolidated per-video cost budget.

## Proposed remediation in this audit PR

- Change `road_follow` to a low, wide, track-follow composition, distinct from the rear telephoto shot.
- Force the road-follow scene into a track environment.
- Add a geometry regression test for road-follow versus rear telephoto.
- Upload partial artifact-gate evidence even when the gate fails.
- Change YouTube duplicate detection to use a media-content fingerprint and scan the complete uploads playlist.
- Add an idempotency regression test.

## Remaining owner-blocked work

- Provide/confirm the Odysseus gateway and YouTube OAuth secrets in GitHub Secrets. The connector does not expose secret values and they must not be copied into source.
- Explicitly authorize unattended public publishing before enabling a scheduled workflow that uploads publicly.
- Inspect a real production MP4 and representative frames (exterior, interior, road scenes, motion, all four Shorts) after a full production run passes.
- Confirm the YouTube channel target and privacy policy.
- Confirm free-tier quota and runtime budget for the chosen schedule.

## Acceptance gate

A successful CI artifact fixture is necessary but not sufficient. Production readiness requires a real generated long video + four Shorts, complete final QA, content-hash idempotency, successful upload evidence, and visual inspection. Public auto-publishing remains disabled until owner authorization.

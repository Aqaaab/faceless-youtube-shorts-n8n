# Automotive AI Content Engine — Agent Instructions

This file is the project-level `AGENT.md` configuration and follows the AGENT.md convention.

## Project Goal

Build an automated automotive YouTube content engine that produces:

- One 7–15 minute long-form automotive video from one topic.
- 25 connected scenes with coherent narration, visuals, timing, and transitions.
- Four Shorts derived from the same content, each 28–59 seconds at 1080×1920.
- Arabic subtitles burned into the rendered video.
- Automated YouTube publishing with metadata and duplicate-upload protection.
- Mandatory technical and visual QA before publishing.

## Non-Negotiable Visual Standard

The target is **Premium Automotive Editorial Video**, not a generic dashboard, SVG presentation, or static technical UI.

The car must be the primary visual subject. Prefer scene-specific automotive imagery with:

- realistic vehicle representation;
- multiple camera angles and meaningful close-ups;
- automotive environments, lighting, depth, reflections, and composition;
- scene-specific specifications, callouts, labels, and overlays only when relevant;
- purposeful motion, camera movement, transitions, and visual progression;
- strong composition suitable for YouTube viewing.

Do not use simplified generic side-profile car drawings as the primary visual treatment. A technically valid render is not sufficient if the visual product is weak.

## Shorts Standard

Shorts must be designed for vertical 1080×1920 composition rather than merely cropping the master video.

- Keep the car and key information visually dominant.
- Avoid excessive empty space.
- Use strong hooks and fast visual progression.
- Keep captions within safe margins.
- Recompose scene elements for vertical viewing.

## Arabic Subtitle Standard

Arabic subtitles are required in the final rendered videos.

- Use readable Arabic typography.
- Keep subtitle size proportional to the frame.
- Do not place subtitles over the main vehicle subject when avoidable.
- Respect safe margins.
- Split lines intelligently.
- Subtitles must remain synchronized with narration.

## Voice / Narration Standard

Narration must suit a fast automotive YouTube format.

Target Arabic narration rate: approximately 1.6–2.1 words/second, with approximately 1.7–2.0 words/second as the normal target.

Do not solve timing only by stretching or compressing audio. Optimize narration wording, scene duration, TTS pacing, pauses, and audio/video synchronization together.

## QA Requirements

Technical gates alone do not make a production-ready video. QA must evaluate both technical validity and visual product quality.

Required checks include:

- 25 connected scenes.
- Master duration within the requested range.
- Four Shorts, each 28–59 seconds.
- Correct 1080×1920 Short resolution.
- Burned Arabic subtitles.
- Valid audio and synchronization.
- No black bars or unintended empty framing.
- No external stock-media dependency.
- No duplicate YouTube upload on reruns.
- Valid metadata and configurable privacy status.
- Visual quality gate that can FAIL a technically valid but visually weak artifact.
- Scene-specific visual relevance.
- Car-first composition.
- Meaningful motion rather than static panels.
- Subtitle readability and safe placement.
- Appropriate narration pacing.

Production/publishing must remain blocked when mandatory QA fails.

## Provider / Architecture Rules

- Odysseus Gateway is the intended AI entry point for this project.
- Do not introduce an unrelated paid provider fallback without an explicit project requirement.
- Do not reintroduce deprecated external stock-asset fallback logic.
- Prefer generated visual assets and deterministic rendering/animation where compatible with the current architecture.
- Preserve existing secrets and environment-variable naming unless a migration is explicitly required.

## Repository Safety

Before changing architecture or deleting existing functionality:

1. Inspect the current repository and workflows.
2. Identify active production paths and tests.
3. Search for deprecated references before removing them.
4. Keep changes internally consistent across pipeline, rendering, QA, validation, and publishing.
5. Do not run production publishing while unresolved validation failures remain.

Never commit API keys, tokens, credentials, or other secrets.

## Required Verification

After substantive changes, verify at minimum:

- `pipeline.py`
- `render.py`
- `qa.py`
- `validator.py`
- `upload.py`
- relevant workflow files
- subtitle generation/burning
- audio duration and pacing
- Short generation and vertical framing
- duplicate-upload protection
- environment-variable/secrets consistency
- removal of obsolete stock-media references

Run the repository's applicable tests and CI checks. Do not declare success based solely on a green technical check if the resulting artifact violates the visual product standard.

## Agent Behavior

Agents must inspect existing code before editing, make changes coherently across dependent components, and verify the final artifact rather than stopping at implementation-level tests.

When a requirement conflicts with an older implementation or legacy reference, the current project requirements in this file take precedence unless the user explicitly requests otherwise.

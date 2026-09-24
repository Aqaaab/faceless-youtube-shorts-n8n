# Blender automotive renderer

The vehicle image backend now uses a deterministic Blender/EEVEE renderer. Pillow remains in the repository only for legacy helpers and image QA; it is no longer the production source of the vehicle frames.

## Runtime contract

- Long scenes: native 1920x1080 PNG.
- Portrait scenes: native 1080x1920 PNG.
- One deterministic procedural 3D vehicle is rebuilt for every render, so the same geometry is reused across all 25 scenes.
- Camera, materials, lights and studio floor are controlled by Blender.
- FFmpeg remains downstream for video assembly and subtitles.
- No image-generation API key is required.
- Every render writes a .blender.json evidence file.

## Asset strategy

The current repository uses a procedural 3D automotive baseline so CI and production do not depend on a third-party model download. This is an explicit deterministic baseline, not a claim of OEM-level photorealism.

A future .blend or .glb can replace build_car() in scripts/blender_automotive_scene.py without changing the Python pipeline contract.

## Local requirements

Install Blender and FFmpeg, or set BLENDER_BIN=/path/to/blender.

The production workflow installs Blender on the GitHub Actions runner.

## Quality gate

A render is accepted only when:

1. Blender is present.
2. PNG exists and is non-trivial.
3. Requested resolution is exact.
4. Renderer metadata identifies blender_eevee_automotive_v2.
5. The existing visual-product and MP4 gates pass.

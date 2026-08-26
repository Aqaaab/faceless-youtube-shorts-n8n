#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess
from pathlib import Path

RUN_DIR = Path(os.environ.get('RUN_DIR', 'data/run'))
RUN_DIR.mkdir(parents=True, exist_ok=True)
OUT = RUN_DIR / 'github_assistants.json'

ASSISTANTS = [
    {'name': 'yt-dlp', 'repo': 'yt-dlp/yt-dlp', 'role': 'YouTube research metadata/search/media retrieval', 'integration': 'research', 'license': 'Unlicense', 'enabled_by_default': True},
    {'name': 'PySceneDetect', 'repo': 'Breakthrough/PySceneDetect', 'role': 'content-aware scene detection and representative frame sampling', 'integration': 'optional-render-qa', 'license': 'BSD-3-Clause', 'enabled_by_default': False},
    {'name': 'WhisperX', 'repo': 'm-bain/whisperX', 'role': 'word-level transcription/alignment for captions and clip boundaries', 'integration': 'optional-transcript-qa', 'license': 'verify-at-integration-time', 'enabled_by_default': False},
    {'name': 'pyannote-audio', 'repo': 'pyannote/pyannote-audio', 'role': 'speaker diarization and speech activity analysis', 'integration': 'optional-audio-qa', 'license': 'MIT', 'enabled_by_default': False},
    {'name': 'YT-Shorts-Automator', 'repo': 'edyahcks/YT-Shorts-Automator', 'role': 'local Whisper/Ollama/FFmpeg short-selection patterns', 'integration': 'research-reference', 'license': 'verify-at-integration-time', 'enabled_by_default': False},
    {'name': 'clipforge-local', 'repo': 'jayadevrana/clipforge-local', 'role': 'local long-video-to-clip experimentation', 'integration': 'research-reference', 'license': 'verify-at-integration-time', 'enabled_by_default': False},
]


def _load_local_state() -> bool:
    state = RUN_DIR / 'ai_router' / 'freellmapi.env'
    if not state.is_file():
        return False
    for line in state.read_text(encoding='utf-8').splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            os.environ[key] = value
    return bool(os.getenv('FREELLMAPI_API_KEY'))


def bootstrap() -> tuple[bool, str]:
    if os.getenv('GITHUB_ACTIONS', '').lower() != 'true':
        return False, 'NON_GITHUB_ACTIONS'
    if os.getenv('ENABLE_LOCAL_FREE_STACK', 'false').lower() != 'true':
        return False, 'OPT_IN_DISABLED'
    if (os.getenv('ENABLE_FREELLMAPI_PROVIDER', 'false').lower() != 'true'
            and os.getenv('ENABLE_OLLAMA_PROVIDER', 'false').lower() != 'true'):
        return False, 'LOCAL_PROVIDERS_DISABLED'

    script = Path(__file__).resolve().parent / 'bootstrap_runtime_free_stack_v2.sh'
    try:
        subprocess.run(['bash', str(script)], check=True, env=os.environ.copy())
    except Exception as exc:
        print(f'LOCAL_FREE_STACK_BOOTSTRAP=SKIP reason={str(exc)[:300]}')
        return False, 'BOOTSTRAP_FAILED'

    if _load_local_state():
        print('FREE_LOCAL_PROVIDER_ENV=LOADED')
        return True, 'READY'

    print('LOCAL_FREE_STACK_BOOTSTRAP=SKIP reason=ENV_NOT_WRITTEN')
    return False, 'ENV_NOT_WRITTEN'


def main():
    bootstrapped, bootstrap_status = bootstrap()
    if not bootstrapped:
        # Remote free providers remain the primary pool. A broken local runtime
        # must never turn into a hard failure of the production planner.
        os.environ['ENABLE_FREELLMAPI_PROVIDER'] = 'false'
        os.environ['ENABLE_OLLAMA_PROVIDER'] = 'false'

    payload = {
        'schema_version': '1.3',
        'mode': 'local_first_optional',
        'assistants': ASSISTANTS,
        'policy': 'External assistants augment internal systems only; they cannot replace Visual QA, Final Feature QA, production contracts, or fail-closed behavior.',
        'local_free_stack': 'Ollama + FreeLLMAPI are opt-in in GitHub Actions and non-blocking when remote free providers are available',
        'local_free_stack_enabled': bootstrapped,
        'local_free_stack_status': bootstrap_status,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'LOCAL_FREE_STACK_BOOTSTRAP={"PASS" if bootstrapped else "SKIP"}')


if __name__ == '__main__':
    main()

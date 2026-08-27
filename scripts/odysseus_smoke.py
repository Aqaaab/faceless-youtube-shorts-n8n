from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}


def _has_fallback() -> bool:
    return bool(os.getenv("GEMINI_API_KEY", "").strip()) or bool(
        os.getenv("YOUTUBE_LLM_BASE_URL", "").strip()
        and os.getenv("YOUTUBE_LLM_API_KEY", "").strip()
    )


def main() -> int:
    base = os.getenv("ODYSSEUS_GATEWAY_BASE_URL", "").strip().rstrip("/")
    key = os.getenv("ODYSSEUS_GATEWAY_API_KEY", "").strip()
    model = os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story").strip() or "aqaaab/story"
    timeout = max(30, int(os.getenv("ODYSSEUS_SMOKE_TIMEOUT", "120")))
    retries = max(0, int(os.getenv("ODYSSEUS_SMOKE_RETRIES", "2")))
    if not base or not key:
        print("ODYSSEUS_SMOKE=SKIP missing gateway configuration")
        return 0

    url = base if base.endswith("/api/v1/chat") else base + "/api/v1/chat"
    payload = {
        "message": json.dumps(
            {
                "task": "health_check",
                "contract": "Return JSON object exactly: {\"ok\":true}",
            },
            separators=(",", ":"),
        ),
        "model": model,
    }

    last_error = "unknown failure"
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8", "replace"))
            result = body.get("response") if isinstance(body, dict) else None
            if not result:
                last_error = "missing response"
            else:
                print(f"ODYSSEUS_SMOKE=PASS model={body.get('model', model)} attempt={attempt + 1}")
                return 0
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:1000]
            last_error = f"http={exc.code} detail={detail}"
            if exc.code not in RETRYABLE_HTTP:
                break
            if attempt < retries:
                print(f"ODYSSEUS_SMOKE=RETRY http={exc.code} attempt={attempt + 1}", flush=True)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = f"transport={exc}"
            if attempt < retries:
                print(f"ODYSSEUS_SMOKE=RETRY transport={exc} attempt={attempt + 1}", flush=True)

        if attempt < retries:
            time.sleep(min(12, 2 ** attempt))

    # A smoke test must report primary degradation, but it must not block a
    # production run when an explicitly configured fallback can take over.
    if _has_fallback():
        print(f"ODYSSEUS_SMOKE=DEGRADED {last_error}; fallback_available=true", flush=True)
        return 0
    print(f"ODYSSEUS_SMOKE=FAIL {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

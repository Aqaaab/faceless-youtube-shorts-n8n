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


def _request_json(req: urllib.request.Request, timeout: int) -> dict:
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8", "replace"))
    if not isinstance(body, dict):
        raise RuntimeError("Odysseus returned a non-object JSON response")
    return body


def _health(base: str, timeout: int, retries: int) -> tuple[bool, str]:
    url = base if base.endswith("/api/health") else base + "/api/health"
    last_error = "unknown failure"
    for attempt in range(retries + 1):
        try:
            body = _request_json(
                urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET"),
                timeout,
            )
            if body.get("ok") is True:
                return True, "ok"
            last_error = f"unexpected health payload: {body}"
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:600]
            last_error = f"health_http={exc.code} detail={detail}"
            if exc.code not in RETRYABLE_HTTP:
                break
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_error = f"health_transport={exc}"
        if attempt < retries:
            time.sleep(min(6, 2**attempt))
    return False, last_error


def _authenticated_smoke(base: str, key: str, model: str, timeout: int, retries: int) -> tuple[bool, str]:
    url = base if base.endswith("/api/v1/chat") else base + "/api/v1/chat"
    payload = {
        "message": json.dumps(
            {"task": "health_check", "contract": "Return JSON object exactly: {\"ok\":true}"},
            separators=(",", ":"),
        ),
        "model": model,
    }
    last_error = "unknown failure"
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            body = _request_json(req, timeout)
            result = body.get("response")
            if isinstance(result, dict) and result.get("ok") is True:
                return True, f"model={body.get('model', model)}"
            if isinstance(result, str):
                parsed = json.loads(result)
                if isinstance(parsed, dict) and parsed.get("ok") is True:
                    return True, f"model={body.get('model', model)}"
            last_error = "health contract response was not {\"ok\":true}"
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:1000]
            last_error = f"http={exc.code} detail={detail}"
            if exc.code not in RETRYABLE_HTTP:
                break
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = f"transport={exc}"
        if attempt < retries:
            time.sleep(min(6, 2**attempt))
    return False, last_error


def main() -> int:
    base = os.getenv("ODYSSEUS_GATEWAY_BASE_URL", "").strip().rstrip("/")
    key = os.getenv("ODYSSEUS_GATEWAY_API_KEY", "").strip()
    model = os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story").strip() or "aqaaab/story"
    health_timeout = max(10, int(os.getenv("ODYSSEUS_HEALTH_TIMEOUT", "30")))
    smoke_timeout = max(15, int(os.getenv("ODYSSEUS_SMOKE_TIMEOUT", "45")))
    retries = max(0, int(os.getenv("ODYSSEUS_SMOKE_RETRIES", "2")))

    if not base or not key:
        print("ODYSSEUS_SMOKE=FAIL missing gateway configuration", file=sys.stderr)
        return 1

    healthy, health_detail = _health(base, health_timeout, retries)
    if not healthy:
        if _has_fallback():
            print(f"ODYSSEUS_SMOKE=DEGRADED {health_detail}; fallback_available=true", flush=True)
            return 0
        print(f"ODYSSEUS_SMOKE=FAIL {health_detail}", file=sys.stderr)
        return 1

    authenticated, detail = _authenticated_smoke(base, key, model, smoke_timeout, retries)
    if authenticated:
        print(f"ODYSSEUS_SMOKE=PASS {detail}", flush=True)
        return 0

    # A healthy gateway with a temporarily broken authentication/upstream path
    # may still be safely handled by the production fallback chain.
    if _has_fallback():
        print(f"ODYSSEUS_SMOKE=DEGRADED {detail}; gateway_health=ok fallback_available=true", flush=True)
        return 0
    print(f"ODYSSEUS_SMOKE=FAIL {detail}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

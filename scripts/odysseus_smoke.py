from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    base = os.getenv("ODYSSEUS_GATEWAY_BASE_URL", "").strip().rstrip("/")
    key = os.getenv("ODYSSEUS_GATEWAY_API_KEY", "").strip()
    model = os.getenv("ODYSSEUS_STORY_MODEL", "aqaaab/story").strip()
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
        with urllib.request.urlopen(req, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1000]
        print(f"ODYSSEUS_SMOKE=FAIL http={exc.code} detail={detail}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"ODYSSEUS_SMOKE=FAIL transport={exc}", file=sys.stderr)
        return 1

    response = body.get("response") if isinstance(body, dict) else None
    if not response:
        print("ODYSSEUS_SMOKE=FAIL missing response", file=sys.stderr)
        return 1
    print(f"ODYSSEUS_SMOKE=PASS model={body.get('model', model)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

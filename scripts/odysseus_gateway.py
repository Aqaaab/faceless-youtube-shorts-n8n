#!/usr/bin/env python3
"""OpenAI-compatible local gateway: Odysseus -> Aqaaab AI Router.

Odysseus never receives individual provider credentials. This process exposes a
small compatibility endpoint and delegates routing to the existing free-only
provider mesh. It is intentionally opt-in and does not alter production unless
ODYSSEUS_GATEWAY_ENABLED=true.
"""
from __future__ import annotations
import json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TASK_BY_MODEL = {
    "aqaaab/idea": "idea",
    "aqaaab/research": "research",
    "aqaaab/hook": "hook",
    "aqaaab/story": "long_story",
    "aqaaab/scene-plan": "scene_plan",
    "aqaaab/qa": "qa",
}


def _json_error(message: str, status: int = 400):
    return status, {"error": {"message": message, "type": "gateway_error"}}


def _route(task: str, prompt: str):
    # The production-safe path currently has a proven fixed-slot router.
    # Other tasks are rejected until their dedicated task router is registered;
    # this prevents silent misuse of the long-story model for unrelated work.
    if task != "long_story":
        raise RuntimeError(f"task router not registered: {task}")
    from ai_router import build_long_story_router
    result, provider, model = build_long_story_router().route(prompt)
    content = json.dumps(result, ensure_ascii=False)
    return content, provider, model


class Handler(BaseHTTPRequestHandler):
    server_version = "Aqaaab-Odysseus-Gateway/1.0"

    def _send(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "gateway": "odysseus", "router": "aqaaab"})
            return
        if self.path == "/v1/models":
            self._send(200, {"object": "list", "data": [{"id": x, "object": "model", "owned_by": "aqaaab"} for x in TASK_BY_MODEL]})
            return
        self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self._send(404, {"error": {"message": "not found"}})
            return
        if os.getenv("ODYSSEUS_GATEWAY_ENABLED", "false").lower() != "true":
            self._send(503, {"error": {"message": "Odysseus gateway disabled"}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            model = str(body.get("model", "aqaaab/story"))
            task = TASK_BY_MODEL.get(model)
            if not task:
                raise ValueError(f"unsupported gateway model: {model}")
            messages = body.get("messages") or []
            prompt = "\n".join(str(m.get("content", "")) for m in messages if isinstance(m, dict))
            content, provider, selected_model = _route(task, prompt)
            self._send(200, {
                "id": "aqaaab-gateway",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                "model": selected_model or model,
                "x_aqaaab_provider": provider,
            })
        except Exception as exc:
            status, payload = _json_error(str(exc), 502)
            self._send(status, payload)

    def log_message(self, fmt, *args):
        print("ODYSSEUS_GATEWAY " + (fmt % args))


def main():
    host = os.getenv("ODYSSEUS_GATEWAY_HOST", "127.0.0.1")
    port = int(os.getenv("ODYSSEUS_GATEWAY_PORT", "8787"))
    print(f"ODYSSEUS_GATEWAY_LISTEN={host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()

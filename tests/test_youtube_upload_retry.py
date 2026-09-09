from __future__ import annotations

import ast
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "youtube_upload.py"


def _upload_function() -> ast.FunctionDef:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_upload")


def test_upload_creates_one_resumable_request_outside_retry_loop() -> None:
    fn = _upload_function()
    loops = [node for node in ast.walk(fn) if isinstance(node, ast.For)]
    assert len(loops) == 1, "upload retry contract expects one retry loop"
    retry_loop = loops[0]

    insert_calls = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "insert"
    ]
    assert len(insert_calls) == 1, "videos.insert must be created once per upload"
    assert not any(insert_calls[0] is node or insert_calls[0] in ast.walk(node) for node in [retry_loop])


def test_upload_retries_same_resumable_session() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert "same_resumable_session=true" in source
    assert "request.next_chunk()" in source
    assert "youtube.videos().insert" in source

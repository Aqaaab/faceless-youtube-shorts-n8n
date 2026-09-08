from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable
from typing import Any


TRANSIENT_EXCEPTIONS = (OSError, TimeoutError, subprocess.CalledProcessError)


def run_gate(name: str, gate: Callable[..., Any], *args: Any) -> Any:
    retries = max(1, int(os.getenv("FINAL_GATE_RETRIES", "2")))
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            result = gate(*args)
            print(f"{name}=PASS attempt={attempt}", flush=True)
            return result
        except TRANSIENT_EXCEPTIONS as exc:
            last_error = exc
            print(
                f"{name}=RETRYABLE_FAIL attempt={attempt}/{retries} "
                f"error={type(exc).__name__}: {exc}",
                flush=True,
            )
            if attempt < retries:
                time.sleep(min(5, attempt * 2))
        except Exception as exc:
            print(
                f"{name}=FAIL attempt={attempt} "
                f"error={type(exc).__name__}: {exc}",
                flush=True,
            )
            raise

    assert last_error is not None
    print(
        f"{name}=FAIL attempts={retries} "
        f"error={type(last_error).__name__}: {last_error}",
        flush=True,
    )
    raise last_error

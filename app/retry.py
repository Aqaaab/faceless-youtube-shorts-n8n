from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


def retry_call(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    retry_if: Callable[[Exception], bool] | None = None,
    label: str = "operation",
) -> T:
    attempts = max(1, int(attempts))
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last = exc
            if attempt >= attempts or (retry_if is not None and not retry_if(exc)):
                raise
            time.sleep(base_delay * (2 ** (attempt - 1)))
    raise RuntimeError(f"{label} failed after {attempts} attempts") from last


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    retry_if: Callable[[Exception], bool] | None = None,
    label: str = "operation",
) -> T:
    attempts = max(1, int(attempts))
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except Exception as exc:
            last = exc
            if attempt >= attempts or (retry_if is not None and not retry_if(exc)):
                raise
            await asyncio.sleep(base_delay * (2 ** (attempt - 1)))
    raise RuntimeError(f"{label} failed after {attempts} attempts") from last

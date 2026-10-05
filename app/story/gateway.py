from __future__ import annotations
import os
import time
import requests
from config.settings import get_float, get_int

TRANSIENT_HTTP = {408, 425, 429, 500, 502, 503, 504}
GATEWAY_TIMEOUT = min(60.0, max(15.0, get_float("ODYSSEUS_UPSTREAM_TIMEOUT", 60.0)))

class OdysseusRateLimitError(RuntimeError):
    """Raised after configured gateway retries are exhausted on HTTP 429."""


def _retry_delay(response: requests.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After", "")
    if retry_after:
        try:
            return max(1.0, min(float(retry_after), 60.0))
        except ValueError:
            pass
    return min(2 ** (attempt - 1), 8)


def ask_odysseus(system: str, user: str, *, timeout: float | None = None, max_attempts: int | None = None) -> dict:
    # ZERO COST GUARANTEE: only Odysseus is called. No paid fallback is permitted.
    base = os.environ["ODYSSEUS_GATEWAY_BASE_URL"].rstrip("/")
    key = os.environ["ODYSSEUS_GATEWAY_API_KEY"]
    url = f"{base}/api/v1/chat"
    payload = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "response_format": {"type": "json_object"}}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}
    attempts = max(3, int(max_attempts) if max_attempts is not None else int(get_int("ODYSSEUS_MAX_ATTEMPTS", 3)))
    requested_timeout = float(timeout if timeout is not None else get_float("ODYSSEUS_REQUEST_TIMEOUT", GATEWAY_TIMEOUT))
    # The workflow health contract stays at <=60s; explicit story/repair calls may run up to 180s.
    request_timeout = min(180.0, max(15.0, requested_timeout))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=request_timeout)
        except requests.RequestException as exc:
            last_error = exc
            if attempt == attempts:
                raise RuntimeError(f"Odysseus network failure after {attempt} attempts: {exc}") from exc
            time.sleep(min(2 ** (attempt - 1), 8))
            continue
        if response.status_code == 429:
            detail = response.text[:1000].replace("\n", " ")
            last_error = OdysseusRateLimitError(f"HTTP 429: {detail}")
            if attempt == attempts:
                raise OdysseusRateLimitError(f"Odysseus rate limit exhausted after {attempts} attempts: {detail}") from last_error
            time.sleep(_retry_delay(response, attempt))
            continue
        if response.status_code in TRANSIENT_HTTP:
            detail = response.text[:1000].replace("\n", " ")
            last_error = RuntimeError(f"HTTP {response.status_code}: {detail}")
            if attempt == attempts:
                raise RuntimeError(f"Odysseus chat failed after {attempts} attempts: {detail}") from last_error
            time.sleep(_retry_delay(response, attempt))
            continue
        if not response.ok:
            detail = response.text[:1500].replace("\n", " ")
            raise RuntimeError(f"Odysseus chat failed HTTP {response.status_code}: {detail}")
        try:
            return _extract_json(_content_from_envelope(response.json()))
        except (ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt == attempts:
                raise RuntimeError(f"Odysseus response contract failed after {attempts} attempts: {exc}") from exc
            time.sleep(min(2 ** (attempt - 1), 8))
    raise RuntimeError(f"Odysseus request failed: {last_error}")



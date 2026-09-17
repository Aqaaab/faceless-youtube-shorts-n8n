import os, time
import requests

GATEWAY_TIMEOUT = 60.0
TRANSIENT_HTTP = {502, 503, 504}


class OdysseusRateLimitError(RuntimeError):
    pass


def _retry_delay(response: requests.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After", "")
    if retry_after:
        try:
            return max(1.0, min(float(retry_after), 60.0))
        except ValueError:
            pass
    return min(2 ** (attempt - 1), 8)


def _extract_content(data: dict) -> str:
    candidates = []
    choices = data.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if isinstance(message, dict):
                candidates.extend([message.get("content"), message.get("text"), message.get("reasoning_content"), message.get("reasoning")])
            first = choice.get("delta")
            if isinstance(first, dict):
                candidates.extend([first.get("text"), first.get("output_text"), first.get("reasoning_content"), first.get("reasoning")])
    candidates.extend([data.get("output_text"), data.get("text"), data.get("reasoning_content"), data.get("reasoning")])
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    for key in ("text", "content", "value"):
                        if isinstance(item.get(key), str):
                            parts.append(item[key])
                            break
            joined = "".join(parts).strip()
            if joined:
                return joined
    raise RuntimeError("Odysseus returned no model content")


def ask_odysseus(system: str, user: str, *, timeout: float | None = None, max_attempts: int | None = None) -> dict:
    # ZERO COST GUARANTEE: only Odysseus is called. No paid fallback is permitted.
    base = os.environ["ODYSSEUS_GATEWAY_BASE_URL"].rstrip("/")
    key = os.environ["ODYSSEUS_GATEWAY_API_KEY"]
    url = f"{base}/api/v1/chat"
    payload = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "response_format": {"type": "json_object"}}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}
    attempts = max(3, int(max_attempts) if max_attempts is not None else int(os.getenv("ODYSSEUS_MAX_ATTEMPTS", "3")))
    # Keep the workflow's default request timeout at 60s, but honor explicit long-running
    # story/repair timeouts up to 180s. The gateway health contract remains <=60s.
    requested_timeout = float(timeout if timeout is not None else os.getenv("ODYSSEUS_REQUEST_TIMEOUT", GATEWAY_TIMEOUT))
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
            detail = response.text[:1000].replace("\n", " ")
            raise RuntimeError(f"Odysseus chat HTTP {response.status_code}: {detail}")
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError("Odysseus returned invalid JSON") from exc
        return data
    raise RuntimeError(f"Odysseus request failed after {attempts} attempts: {last_error}")

"""API helpers shared by the builder and the grader: the OpenAI Responses client (the key comes from
OPENAI_API_KEY), strict function tools, token usage, a JSONL recorder and one forced-tool call with
retries. Offline tests pass a fake client with `responses.create` and never create a real one."""
import json
import os
import random
import threading
import time
from collections import Counter
from pathlib import Path

import config as C


def client():
    import openai
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("set OPENAI_API_KEY (see env.example.sh at the repository root)")
    return openai.OpenAI(api_key=key, timeout=3600, max_retries=3)


def fn(name: str, description: str, **props) -> dict:
    """A strict function tool: every property required, nothing else allowed."""
    return {"type": "function", "name": name, "description": description, "strict": True,
            "parameters": {"type": "object", "properties": props,
                           "required": list(props), "additionalProperties": False}}


def usage_of(resp) -> Counter:
    u, out = getattr(resp, "usage", None), Counter()
    if u is None:
        return out
    out["input_tokens"] += getattr(u, "input_tokens", 0) or 0
    out["output_tokens"] += getattr(u, "output_tokens", 0) or 0
    out["cached_tokens"] += getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0
    out["reasoning_tokens"] += getattr(getattr(u, "output_tokens_details", None), "reasoning_tokens", 0) or 0
    return out


def usage_sum(*counters) -> dict:
    total = Counter()
    for c in counters:
        total += Counter(c)
    return dict(total)


class ApiError(RuntimeError):
    """A request that cannot be made or answered. fatal: stop everything (quota used up, malformed request)."""

    def __init__(self, message, fatal=False):
        super().__init__(message)
        self.fatal = fatal


TRANSIENT = ("APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError")


def create(cl, log, record=None, **kw):
    """One Responses API call. Rate limits, timeouts and server errors are waited out (at most
    API_RETRIES times); a used-up quota or a rejected request is fatal."""
    for attempt in range(1, C.API_RETRIES + 1):
        try:
            return cl.responses.create(**kw)
        except Exception as exc:
            if getattr(exc, "code", None) == "insufficient_quota" or "insufficient_quota" in str(exc):
                raise ApiError("the API quota is used up (insufficient_quota)", fatal=True) from None
            if type(exc).__name__ not in TRANSIENT:
                raise ApiError(f"the API rejected the request: {type(exc).__name__}: {str(exc)[:200]}",
                               fatal=True) from None
            wait = min(600, 30 * 2 ** (attempt - 1)) * random.uniform(0.8, 1.2)
            if log:
                log.warning(f"OpenAI API: {type(exc).__name__} (attempt {attempt}): retrying in {wait:.0f}s")
            if record:
                record({"event": "api_wait", "error": type(exc).__name__, "attempt": attempt,
                        "wait_s": round(wait), "time": time.strftime("%Y-%m-%d %H:%M:%S")})
            time.sleep(wait)
    raise ApiError(f"the API kept failing after {C.API_RETRIES} tries", fatal=True)


class Recorder:
    """sessions.jsonl of one problem or one grading, appended to from several threads."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def __call__(self, obj: dict):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")


def respond(cl, log, record, role: str, **kw):
    """One forced-tool call; a failed or incomplete response is asked again (3 times)."""
    for attempt in range(1, 4):
        resp = create(cl, log, record, **kw)
        record({"role": role, "event": "response", "id": getattr(resp, "id", None),
                "status": getattr(resp, "status", None), "usage": dict(usage_of(resp)),
                "output": [o.model_dump() if hasattr(o, "model_dump") else str(o) for o in resp.output],
                "time": time.strftime("%Y-%m-%d %H:%M:%S")})
        if getattr(resp, "status", None) == "completed":
            return resp
        if log:
            log.warning(f"{role}: response {getattr(resp, 'status', None)}; asking again ({attempt}/3)")
        time.sleep(20)
    raise ApiError(f"{role}: no completed response after 3 tries")


def function_call(resp):
    """The function call of a response, or None."""
    return next((o for o in getattr(resp, "output", None) or []
                 if getattr(o, "type", None) == "function_call"), None)

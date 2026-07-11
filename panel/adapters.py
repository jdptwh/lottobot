"""OpenRouter provider adapter — one call, normalized result, cost included.

A single-expert building block: `call_model` sends one OpenAI-compatible chat
request to OpenRouter and returns a normalized `ModelResult`. Parallel fan-out
of multiple experts is Wave 3's orchestrator, not here.

Design points (all from docs/openrouter_api_notes_wave2.md, verified 2026-07-07):
  * Usage accounting is always on (`"usage": {"include": true}`) so the response
    carries the authoritative `usage.cost` — the cost_meter's ground truth.
  * Errors are classified from the PARSED BODY first, HTTP status second, because
    OpenRouter can return HTTP 200 with an `{"error": {...}}` body.
  * The network seam is an injectable `transport` callable, so unit tests never
    touch the network and the default gate spends nothing.
  * stdlib only (urllib) — no runtime dependency (Wave 2 ruling (a)).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable, Optional

from panel.errors import (
    MissingAPIKeyError,
    TransientProviderError,
    classify,
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# transport(url, data_bytes, headers) -> (status: int | None, body_bytes: bytes)
Transport = Callable[[str, bytes, dict], "tuple[Optional[int], bytes]"]


@dataclass(frozen=True)
class ModelResult:
    """Normalized result of a single model call."""
    model: str
    content: str
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    cost_usd: Optional[float]
    raw: dict


def _urllib_transport(url: str, data: bytes, headers: dict):
    """Default transport over stdlib urllib. Constructed lazily so importing this
    module (and the whole mocked test gate) never opens a socket."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (fixed host)
            return getattr(resp, "status", resp.getcode()), resp.read()
    except urllib.error.HTTPError as e:
        # HTTPError carries the status code and a readable error body — parse it
        # like any other response so classify() can see error.code.
        return e.code, e.read()
    except urllib.error.URLError as e:
        # Connection-level failure (DNS/refused/reset): no HTTP status. Treat as
        # transient so safe_retry backs off.
        raise TransientProviderError(f"connection error: {e.reason}", code=None) from e


def call_model(
    model: str,
    messages: list,
    *,
    response_format: Optional[dict] = None,
    provider: Optional[dict] = None,
    max_tokens: Optional[int] = None,
    api_key: Optional[str] = None,
    transport: Optional[Transport] = None,
    extra_headers: Optional[dict] = None,
) -> ModelResult:
    """Call one model via OpenRouter and return a normalized ModelResult.

    Raises MissingAPIKeyError (before any transport call) if no key is available,
    TransientProviderError / TerminalProviderError on provider errors (including
    HTTP-200-with-error bodies and empty "no content" responses).
    """
    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise MissingAPIKeyError(
            "OPENROUTER_API_KEY not set and no api_key argument provided"
        )

    body: dict = {"model": model, "messages": messages, "usage": {"include": True}}
    if response_format is not None:
        body["response_format"] = response_format
    if provider is not None:
        body["provider"] = provider
    if max_tokens is not None:
        body["max_tokens"] = max_tokens

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)

    tx = transport or _urllib_transport
    data = json.dumps(body).encode("utf-8")
    status, body_bytes = tx(OPENROUTER_URL, data, headers)

    parsed: dict
    try:
        parsed = json.loads(body_bytes) if body_bytes else {}
    except (json.JSONDecodeError, TypeError):
        parsed = {}

    # 1) error in the body (works for HTTP 200-with-error AND non-2xx bodies)
    if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
        err = parsed["error"]
        raise classify(status, parsed)(
            str(err.get("message", "provider error")),
            code=err.get("code"),
            raw=parsed,
        )

    # 2) non-2xx status without a structured error body
    if status is not None and not (200 <= status < 300):
        raise classify(status, parsed)(f"HTTP {status}", code=status, raw=parsed)

    # 3) success shape — but guard the "no content generated" cold start
    choices = parsed.get("choices") or []
    content = None
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content")
    if not content:
        raise TransientProviderError("no content generated", code=None, raw=parsed)

    usage = parsed.get("usage") or {}
    cost = usage.get("cost")
    return ModelResult(
        model=model,
        content=content,
        tokens_in=usage.get("prompt_tokens"),
        tokens_out=usage.get("completion_tokens"),
        cost_usd=float(cost) if isinstance(cost, (int, float)) else None,
        raw=parsed,
    )

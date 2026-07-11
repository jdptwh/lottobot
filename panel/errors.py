"""Typed provider errors + the transient/terminal classifier.

The classifier is the spine of the retry contract: safe_retry decides whether to
back off and retry (TransientProviderError) or give up immediately
(TerminalProviderError) purely by exception type. Fail-closed: any status/code we
do not explicitly recognize as transient is treated as terminal, so an
unclassified error can never cause an infinite retry loop.

Verified error sets (docs/openrouter_api_notes_wave2.md, 2026-07-07):
  transient: 408 timeout, 429 rate-limit, 502 model down, 503 no provider,
             plus "no content generated" cold starts (handled in adapters).
  terminal:  400 bad request, 401 invalid creds, 402 out of credits,
             403 moderation-flagged.
"""
from __future__ import annotations


class PanelError(Exception):
    """Base for all panel errors."""


class MissingAPIKeyError(PanelError):
    """Neither an explicit api_key nor OPENROUTER_API_KEY was available."""


class ProviderError(PanelError):
    """An error returned by (or while reaching) the provider."""

    def __init__(self, message: str, *, code: int | None = None, raw: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.raw = raw


class TransientProviderError(ProviderError):
    """Retryable: rate limit / timeout / upstream unavailable / cold start."""


class TerminalProviderError(ProviderError):
    """Not retryable: bad request / auth / credits / moderation / unknown."""


TRANSIENT_CODES = frozenset({408, 429, 502, 503})
TERMINAL_CODES = frozenset({400, 401, 402, 403})


def classify(status: int | None, body: dict | None) -> type[ProviderError]:
    """Return the ProviderError subclass for a (status, parsed-body) pair.

    The parsed body's ``error.code`` takes precedence over the HTTP status,
    because OpenRouter can return HTTP 200 with an ``{"error": {...}}`` body
    (a mid-generation failure). Unknown codes fail closed to terminal.
    """
    code: int | None = None
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            c = err.get("code")
            if isinstance(c, bool):
                c = None
            if isinstance(c, int):
                code = c
            elif isinstance(c, str) and c.isdigit():
                code = int(c)
    if code is None:
        code = status
    if code in TRANSIENT_CODES:
        return TransientProviderError
    return TerminalProviderError

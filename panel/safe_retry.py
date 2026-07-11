"""Retry only the transient failures, and only because panel calls are read-only.

The panel is stateless and side-effect-free, so re-issuing a call is always safe
(V5_PLAN Key Finding / OpenRouter runAgentWithRetry semantics). This wrapper
retries ONLY TransientProviderError with jittered exponential backoff; it re-raises
TerminalProviderError (and any non-PanelError) immediately — never loop on a bad
request, auth failure, out-of-credits, or moderation block. A max_total_wait_s
guard bounds worst-case wall time even if a classification is ever wrong.

`sleep` and `rng` are injectable so tests are instant and deterministic.
"""
from __future__ import annotations

import random
import time
from typing import Callable

from panel.errors import TransientProviderError


def call_with_retry(
    fn: Callable,
    *,
    max_attempts: int = 4,
    base_delay_s: float = 0.5,
    max_delay_s: float = 8.0,
    max_total_wait_s: float = 20.0,
    sleep: Callable[[float], None] = time.sleep,
    rng: Callable[[], float] = random.random,
):
    """Call fn() with retry-on-transient. Returns fn()'s result, or re-raises.

    Backoff (pre-jitter): base_delay_s * 2**(attempt-1), capped at max_delay_s.
    Jitter: delay * (0.5 + 0.5*rng()). Stops at max_attempts, or before a sleep
    that would push cumulative wait past max_total_wait_s; then re-raises the last
    TransientProviderError. TerminalProviderError and any other exception propagate
    immediately with no sleep.
    """
    total_wait = 0.0
    last_exc: TransientProviderError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except TransientProviderError as e:
            last_exc = e
            if attempt >= max_attempts:
                break
            delay = min(max_delay_s, base_delay_s * (2 ** (attempt - 1)))
            delay *= 0.5 + 0.5 * rng()
            if total_wait + delay > max_total_wait_s:
                break
            total_wait += delay
            sleep(delay)
    assert last_exc is not None  # only reachable after a TransientProviderError
    raise last_exc

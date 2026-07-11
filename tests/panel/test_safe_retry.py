"""Wave 2 — safe_retry unit tests. Sleep and rng are injected: no real waiting."""
import pytest

from panel.errors import TerminalProviderError, TransientProviderError
from panel.safe_retry import call_with_retry


class Flaky:
    """Callable that raises the given exceptions in sequence, then returns `final`."""
    def __init__(self, raises, final="ok"):
        self._raises = list(raises)
        self._final = final
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self._raises:
            raise self._raises.pop(0)
        return self._final


def recorder():
    delays = []
    return delays, (lambda d: delays.append(d))


def test_transient_then_success():
    delays, sleep = recorder()
    fn = Flaky([TransientProviderError("t", code=429), TransientProviderError("t", code=503)])
    out = call_with_retry(fn, sleep=sleep, rng=lambda: 1.0)
    assert out == "ok"
    assert fn.calls == 3
    assert len(delays) == 2                      # slept once per retry, not on success
    assert all(d >= 0 for d in delays)


def test_terminal_raises_immediately_zero_sleeps():
    delays, sleep = recorder()
    fn = Flaky([TerminalProviderError("bad", code=400)])
    with pytest.raises(TerminalProviderError):
        call_with_retry(fn, sleep=sleep, rng=lambda: 1.0)
    assert fn.calls == 1
    assert delays == []


def test_non_panel_error_propagates():
    delays, sleep = recorder()

    def boom():
        raise ValueError("unexpected")

    with pytest.raises(ValueError):
        call_with_retry(boom, sleep=sleep, rng=lambda: 1.0)
    assert delays == []


def test_exhaustion_reraises_last_transient():
    delays, sleep = recorder()
    fn = Flaky([TransientProviderError(f"t{i}", code=429) for i in range(10)])
    with pytest.raises(TransientProviderError):
        call_with_retry(fn, max_attempts=4, sleep=sleep, rng=lambda: 1.0)
    assert fn.calls == 4                          # max_attempts
    assert len(delays) == 3                       # slept between the 4 attempts


def test_backoff_is_bounded_and_capped():
    delays, sleep = recorder()
    fn = Flaky([TransientProviderError("t", code=429) for _ in range(10)])
    with pytest.raises(TransientProviderError):
        call_with_retry(fn, max_attempts=6, base_delay_s=0.5, max_delay_s=2.0,
                        max_total_wait_s=100.0, sleep=sleep, rng=lambda: 1.0)
    # pre-jitter: 0.5,1.0,2.0,2.0,2.0 (capped at max_delay_s); rng=1.0 -> full delay
    assert delays == [0.5, 1.0, 2.0, 2.0, 2.0]
    assert max(delays) <= 2.0


def test_max_total_wait_stops_early():
    delays, sleep = recorder()
    fn = Flaky([TransientProviderError("t", code=429) for _ in range(10)])
    with pytest.raises(TransientProviderError):
        call_with_retry(fn, max_attempts=10, base_delay_s=1.0, max_delay_s=8.0,
                        max_total_wait_s=3.0, sleep=sleep, rng=lambda: 1.0)
    # delays 1.0, 2.0 -> cumulative 3.0; next would be 4.0 -> 3.0+4.0>3.0 -> stop
    assert sum(delays) <= 3.0

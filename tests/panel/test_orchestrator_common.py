"""Wave 3 — cross-cutting orchestrator tests: cost, cap, partial failure, retry,
no-network, stdlib-only."""
import socket

import pytest

import panel.orchestrator as orch
from panel.errors import TerminalProviderError, TransientProviderError
from orch_fakes import FakeCallModel, expert_plan, synth

DEEPSEEK = "deepseek/deepseek-v4-pro"
GPT = "openai/gpt-5.5"
OPUS = "anthropic/claude-opus-4.8"
THIRD = "google/gemini-3.1-flash-lite"


def plan_fake(cost=0.001, synth_cost=0.002, extra=None):
    r = {
        DEEPSEEK: (expert_plan(summary="ds"), cost),
        GPT: (expert_plan(summary="gpt"), cost),
        OPUS: (synth(), synth_cost),
    }
    if extra:
        r.update(extra)
    return FakeCallModel(r)


# ---- cost metering -----------------------------------------------------------

def test_cost_total_sums_all_calls():
    fake = plan_fake(cost=0.01, synth_cost=0.03)
    v = orch.run_plan("t", "x", [DEEPSEEK, GPT], OPUS, call_model=fake, seed=1, cap_usd=10.0)
    # two experts @0.01 + synth @0.03 = 0.05
    assert abs(v["cost_usd_total"] - 0.05) < 1e-9
    assert v["cost_cap_breached"] is False


def test_cap_breach_after_experts_skips_synth(lint_exit):
    # two experts @0.03 = 0.06 > cap 0.05 -> breach before synth
    fake = plan_fake(cost=0.03, synth_cost=0.02)
    v = orch.run_plan("t", "x", [DEEPSEEK, GPT], OPUS, call_model=fake, seed=1, cap_usd=0.05)
    assert v["cost_cap_breached"] is True
    assert OPUS not in fake.models_called()        # synth never called
    assert v["synthesis"]["artifact"] is None
    assert lint_exit(v)[0] == 2                     # cost_cap -> exit 2


# ---- partial failure ---------------------------------------------------------

def test_one_expert_fails_proceeds_with_survivors(lint_exit):
    # 3-expert lineup, one terminal-errors -> 2 survive -> panel proceeds
    fake = FakeCallModel({
        DEEPSEEK: (expert_plan(summary="ds"), 0.001),
        GPT: (expert_plan(summary="gpt"), 0.001),
        THIRD: TerminalProviderError("boom", code=400),
        OPUS: (synth(), 0.002),
    })
    v = orch.run_plan("t", "x", [DEEPSEEK, GPT, THIRD], OPUS, call_model=fake, seed=1, cap_usd=10.0)
    assert len(v["expert_opinions"]) == 2
    assert any("dropped expert" in b for b in v["disagreement_summary"]["blind_spots"])
    assert OPUS in fake.models_called()            # synth still ran
    assert lint_exit(v)[0] in (0, 1, 2)            # valid verdict


def test_fewer_than_two_survivors_is_structured_revise(lint_exit):
    fake = FakeCallModel({
        DEEPSEEK: (expert_plan(), 0.001),
        GPT: TerminalProviderError("boom", code=400),
        OPUS: (synth(), 0.002),
    })
    v = orch.run_plan("t", "x", [DEEPSEEK, GPT], OPUS, call_model=fake, seed=1, cap_usd=10.0)
    assert v["verdict"] == "REVISE"
    assert OPUS not in fake.models_called()        # no synth on a non-panel
    assert v["synthesis"]["artifact"] is None
    assert len(v["expert_opinions"]) >= 1          # schema minItems=1 preserved
    assert lint_exit(v)[0] == 2


def test_unparseable_expert_counts_as_failure(lint_exit):
    fake = FakeCallModel({
        DEEPSEEK: ("this is not json", 0.001),      # unparseable -> failed expert
        GPT: (expert_plan(), 0.001),
        OPUS: (synth(), 0.002),
    })
    v = orch.run_plan("t", "x", [DEEPSEEK, GPT], OPUS, call_model=fake, seed=1, cap_usd=10.0)
    # only 1 survivor -> structured REVISE
    assert v["verdict"] == "REVISE"
    assert lint_exit(v)[0] == 2


# ---- retry integration -------------------------------------------------------

def test_transient_then_success_retries():
    fake = FakeCallModel({
        DEEPSEEK: [TransientProviderError("rate", code=429), (expert_plan(), 0.001)],
        GPT: (expert_plan(), 0.001),
        OPUS: (synth(), 0.002),
    })
    v = orch.run_plan("t", "x", [DEEPSEEK, GPT], OPUS, call_model=fake, seed=1, cap_usd=10.0)
    # deepseek called twice (retry), then succeeded -> 2 survivors
    assert fake.models_called().count(DEEPSEEK) == 2
    assert len(v["expert_opinions"]) == 2


# ---- no network + stdlib-only ------------------------------------------------

def test_full_orchestration_opens_no_socket(monkeypatch):
    def no_connect(self, *a, **k):
        raise AssertionError("socket.connect called — orchestrator attempted network")

    monkeypatch.setattr(socket.socket, "connect", no_connect)
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("urlopen called")))
    fake = plan_fake()
    v = orch.run_plan("t", "x", [DEEPSEEK, GPT], OPUS, call_model=fake, seed=1, cap_usd=10.0)
    assert v["verdict"] in ("PASS", "FAIL", "REVISE")


def test_orchestrator_imports_only_stdlib_and_panel():
    import panel.orchestrator as o
    src = open(o.__file__).read()
    for banned in ("import requests", "import httpx", "import aiohttp", "import numpy"):
        assert banned not in src
    # concurrency is the stdlib executor
    assert "concurrent.futures" in src

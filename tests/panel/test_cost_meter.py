"""Wave 2 — cost meter unit tests."""
import math

import pytest

from panel.adapters import ModelResult
from panel.cost_meter import CostMeter, DEFAULT_COST_CAP_USD


def mr(cost=None, model="deepseek/deepseek-v4-pro", tin=1000, tout=1000):
    return ModelResult(model=model, content="x", tokens_in=tin, tokens_out=tout, cost_usd=cost, raw={})


def test_usage_cost_is_ground_truth_and_sums():
    m = CostMeter(cap_usd=10.0)
    m.add(mr(cost=0.0123))
    m.add(mr(cost=0.02))
    assert math.isclose(m.total, 0.0323, rel_tol=1e-9)


def test_accepts_raw_usage_dict():
    m = CostMeter(cap_usd=10.0)
    added = m.add({"cost": 0.5, "prompt_tokens": 10, "completion_tokens": 5})
    assert added == 0.5 and m.total == 0.5


def test_breach_boundary():
    m = CostMeter(cap_usd=0.05)
    m.add(mr(cost=0.05))
    assert m.total == 0.05
    assert m.breached is False        # equal to cap is NOT breached
    m.add(mr(cost=0.00001))
    assert m.breached is True         # strictly over cap


def test_fallback_uses_price_table_when_cost_absent():
    # deepseek-v4-pro = (0.435, 0.87) per 1M; 1M in + 1M out -> 0.435 + 0.87
    m = CostMeter(cap_usd=10.0)
    added = m.add(mr(cost=None, model="deepseek/deepseek-v4-pro", tin=1_000_000, tout=1_000_000))
    assert math.isclose(added, 0.435 + 0.87, rel_tol=1e-9)


def test_ground_truth_precedence_ignores_price_table():
    # cost present -> price table must be ignored even though tokens are huge
    m = CostMeter(cap_usd=10.0)
    added = m.add(mr(cost=0.001, model="deepseek/deepseek-v4-pro", tin=9_000_000, tout=9_000_000))
    assert added == 0.001


def test_injected_price_table():
    m = CostMeter(cap_usd=10.0, price_table={"custom/model": (2.0, 4.0)})
    added = m.add(mr(cost=None, model="custom/model", tin=1_000_000, tout=1_000_000))
    assert math.isclose(added, 6.0, rel_tol=1e-9)


def test_per_call_price_override():
    m = CostMeter(cap_usd=10.0)
    added = m.add(mr(cost=None, model="unknown/slug", tin=1_000_000, tout=0), price=(3.0, 9.0))
    assert math.isclose(added, 3.0, rel_tol=1e-9)


def test_no_cost_no_price_raises_rather_than_undercount():
    m = CostMeter(cap_usd=10.0)
    with pytest.raises(ValueError):
        m.add(mr(cost=None, model="unknown/slug", tin=10, tout=10))


def test_default_cap_constant():
    assert CostMeter().cap_usd == DEFAULT_COST_CAP_USD == 2.00
    assert CostMeter(cap_usd=0.05).cap_usd == 0.05

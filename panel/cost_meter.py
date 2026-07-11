"""Cost accumulator with a hard cap.

Ground truth is the response's `usage.cost` (USD actually charged by OpenRouter).
Only when a provider omits `usage.cost` does the meter fall back to
tokens x list-price, using panel/prices.py (or an injected price table / an
explicit per-call price override). The cap value is a plain constructor argument
defaulting to DEFAULT_COST_CAP_USD — Wave 2 does NOT read a PANEL_* config key
(Wave 4 owns configuration).
"""
from __future__ import annotations

import math
from typing import Optional

from panel.prices import VERIFIED_PRICES

DEFAULT_COST_CAP_USD = 2.00


class CostMeter:
    def __init__(self, cap_usd: float = DEFAULT_COST_CAP_USD, price_table: Optional[dict] = None):
        self.cap_usd = cap_usd
        self._price_table = price_table if price_table is not None else VERIFIED_PRICES
        self._total = 0.0

    def add(self, item, *, price: Optional[tuple] = None) -> float:
        """Accumulate one call's cost. `item` may be a ModelResult or a raw
        `usage` dict. `price` (input_per_1m, output_per_1m) overrides the price
        table for this call's fallback. Returns the cost added.

        Raises ValueError if there is neither a usage.cost nor enough information
        (model + tokens + a price) to compute a fallback — silently under-counting
        cost would defeat the cap.
        """
        cost = self._extract_cost(item, price)
        self._total += cost
        return cost

    def _extract_cost(self, item, price: Optional[tuple]) -> float:
        # Pull fields from either a ModelResult or a usage dict.
        cost_usd = getattr(item, "cost_usd", None)
        model = getattr(item, "model", None)
        tin = getattr(item, "tokens_in", None)
        tout = getattr(item, "tokens_out", None)
        if isinstance(item, dict):
            cost_usd = item.get("cost", cost_usd)
            tin = item.get("prompt_tokens", tin)
            tout = item.get("completion_tokens", tout)
            model = item.get("model", model)

        # Ground truth wins whenever present — but only when it is SANE. A
        # malformed provider usage block (negative, NaN, inf, non-numeric) must
        # not poison the accumulator: NaN makes `total > cap` permanently false and a
        # negative "refund" reduces spend — both silent cap bypasses (audit fix).
        # Insane values fall through to the price-table fallback (or the loud
        # ValueError below) instead of being trusted.
        if cost_usd is not None:
            try:
                c = float(cost_usd)
            except (TypeError, ValueError):
                c = float("nan")
            if math.isfinite(c) and c >= 0:
                return c

        # Fallback: tokens x price.
        p = price or (self._price_table.get(model) if model else None)
        if p and tin is not None and tout is not None:
            pin, pout = p
            return (tin / 1_000_000.0) * pin + (tout / 1_000_000.0) * pout

        raise ValueError(
            f"cannot meter cost: no usage.cost and no fallback price for model={model!r} "
            f"(tokens_in={tin}, tokens_out={tout})"
        )

    @property
    def total(self) -> float:
        return self._total

    @property
    def breached(self) -> bool:
        return self._total > self.cap_usd

"""Wave 2 — price table sanity (fallback-only; usage.cost is ground truth)."""
from panel.prices import VERIFIED_ON, VERIFIED_PRICES, price_for


def test_table_non_empty_and_includes_smoke_slug():
    assert VERIFIED_PRICES
    assert "deepseek/deepseek-v4-flash" in VERIFIED_PRICES     # the live-smoke model


def test_entries_are_positive_pairs():
    for slug, pair in VERIFIED_PRICES.items():
        assert len(pair) == 2
        pin, pout = pair
        assert pin > 0 and pout > 0, slug


def test_price_for_lookup():
    assert price_for("deepseek/deepseek-v4-flash") == (0.09, 0.18)
    assert price_for("no/such-model") is None


def test_verification_date_recorded():
    assert VERIFIED_ON == "2026-07-09"    # GPT-5.6 family added (launch-day verify)

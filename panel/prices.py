"""Fallback price table — usage.cost is GROUND TRUTH; this is used only when a
provider omits usage.cost from the response.

Transcribed from docs/openrouter_models_verified_2026-07-09.md (GPT-5.6 additions)
over the 2026-07-07 baseline.
Re-verify against docs/openrouter_models_verified_*.md at each API-touching wave
(V5_PLAN standing rule) — prices drift, and this table is a best-effort fallback,
never the primary accounting source.

Values are USD per 1,000,000 tokens: slug -> (input_per_1m, output_per_1m).
"""
from __future__ import annotations

VERIFIED_ON = "2026-07-09"

VERIFIED_PRICES: dict[str, tuple[float, float]] = {
    "anthropic/claude-fable-5": (10.0, 50.0),
    "anthropic/claude-opus-4.8": (5.0, 25.0),
    "anthropic/claude-opus-4.8-fast": (10.0, 50.0),
    "openai/gpt-5.5": (5.0, 30.0),
    # GPT-5.6 family (launched + verified on OpenRouter 2026-07-09). Sol=flagship,
    # Terra=balanced, Luna=fast/cheap. -pro variants list the SAME per-token price
    # but burn far more reasoning tokens — budget accordingly before lining one up.
    "openai/gpt-5.6-sol": (5.0, 30.0),
    "openai/gpt-5.6-sol-pro": (5.0, 30.0),
    "openai/gpt-5.6-terra": (2.5, 15.0),
    "openai/gpt-5.6-terra-pro": (2.5, 15.0),
    "openai/gpt-5.6-luna": (1.0, 6.0),
    "openai/gpt-5.6-luna-pro": (1.0, 6.0),
    "deepseek/deepseek-v4-pro": (0.435, 0.87),
    "deepseek/deepseek-v4-flash": (0.09, 0.18),
    "moonshotai/kimi-k2.6": (0.95, 4.0),          # multi-provider; ~$0.73-0.95 in / ~$3.49-4.0 out
    "google/gemini-3.1-flash-lite": (0.25, 1.5),
}


def price_for(slug: str) -> tuple[float, float] | None:
    """(input_per_1m, output_per_1m) for a slug, or None if unknown."""
    return VERIFIED_PRICES.get(slug)

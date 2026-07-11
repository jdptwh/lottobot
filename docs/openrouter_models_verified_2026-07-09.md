# OpenRouter model verification — 2026-07-09

Verified live against `GET https://openrouter.ai/api/v1/models` (public endpoint)
on 2026-07-09, the GPT-5.6 launch day. Supersedes the 2026-07-07 baseline for the
slugs below; everything not listed here is unchanged from that document.

## GPT-5.6 family (new today; all six live on OpenRouter)

OpenAI's three-tier family — Sol (flagship; only tier with max reasoning effort /
ultra mode), Terra (balanced, ~GPT-5.5 performance at half the price), Luna
(fast/cheap). Dated snapshots (`...-20260709`) also exist; we configure the
undated aliases, same convention as `openai/gpt-5.5`.

| slug | $/1M in | $/1M out | context |
|---|---|---|---|
| `openai/gpt-5.6-sol` | 5.00 | 30.00 | 1,050,000 |
| `openai/gpt-5.6-sol-pro` | 5.00 | 30.00 | 1,050,000 |
| `openai/gpt-5.6-terra` | 2.50 | 15.00 | 1,050,000 |
| `openai/gpt-5.6-terra-pro` | 2.50 | 15.00 | 1,050,000 |
| `openai/gpt-5.6-luna` | 1.00 | 6.00 | 1,050,000 |
| `openai/gpt-5.6-luna-pro` | 1.00 | 6.00 | 1,050,000 |

CAUTION: the `-pro` variants list the same per-token price as their base tier but
spend substantially more reasoning tokens per request — effective cost is higher
and slower. Do not line one up without headroom under `PANEL_MAX_COST_USD`.

## Re-verified unchanged

- `anthropic/claude-fable-5` — $10/$50
- `anthropic/claude-opus-4.8` — $5/$25
- `openai/gpt-5.5` — $5/$30 (still live; superseded as the panel's OpenAI expert)

## Lineup decision (this date)

- PLAN: `anthropic/claude-fable-5, openai/gpt-5.6-sol` — Sol replaces 5.5 at the
  same price point as the strongest OpenAI planner.
- REVIEW: `anthropic/claude-opus-4.8, openai/gpt-5.6-sol, openai/gpt-5.6-terra` —
  three-reviewer union; Terra added for diversity at half Sol's price (union+arbiter
  benefits from an extra independent perspective more than synthesis does).
- Synth (`opus-4.8`) and arbiter (`fable-5`) unchanged.

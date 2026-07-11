# OpenRouter model IDs & pricing — verified 2026-07-07

Source: `GET https://openrouter.ai/api/v1/models` and per-model `/endpoints`,
fetched 2026-07-07. This supersedes the baseline figures in `V5_PLAN.md §E` per the
standing rule: **specs use live OpenRouter values, not the plan's numbers.**
Re-verify at each API-touching wave's spec time (Waves 2–3), since prices drift.

## Key correction: two different ID namespaces
- **Claude Code / `agent.config`** uses Anthropic-native strings, hyphenated:
  `claude-opus-4-8`, `sonnet`, `haiku`. (This is what the PLANNER/REVIEWER subagents run.)
- **OpenRouter (what the panel calls)** uses dotted slugs: `anthropic/claude-opus-4.8`.
  The `panel_verdict.json` records OpenRouter slugs, NOT Anthropic-native strings.
  V5_PLAN.md's schema example already used the OpenRouter form — keep it.

## Verified slugs + list-price (USD per 1M tokens)

| Role in lineups | OpenRouter slug | in $/M | out $/M | vs. plan baseline |
|---|---|---|---|---|
| PLAN expert / arbiter (Fable) | `anthropic/claude-fable-5` | 10.00 | 50.00 | matches ($10/$50) |
| Synthesizer / reviewer (Opus) | `anthropic/claude-opus-4.8` | 5.00 | 25.00 | matches ($5/$25) |
| Opus Fast Mode | `anthropic/claude-opus-4.8-fast` | 10.00 | 50.00 | matches |
| PLAN/REVIEW expert (GPT) | `openai/gpt-5.5` | 5.00 | 30.00 | matches ($5/$30) |
| Mid/budget expert (DeepSeek) | `deepseek/deepseek-v4-pro` | 0.435 | 0.87 | matches ($0.435/$0.87) |
| Budget expert (Kimi) | `moonshotai/kimi-k2.6` | 0.73–0.95* | 3.49–4.00* | plan flagged as assumption; now confirmed low-cost |
| Budget expert (Gemini flash) | `google/gemini-3.1-flash-lite` | 0.25 | 1.50 | plan said "Gemini 3 Flash"; plain slug absent — flash-lite is the current flash tier |
| (cheaper DeepSeek option) | `deepseek/deepseek-v4-flash` | 0.09 | 0.18 | not in plan; noted for budget lineup |

\* Kimi K2.6 is multi-provider on OpenRouter; price varies by routed provider
(Io Net cheapest at $0.73/$3.49; Moonshot/Fireworks ~$0.95/$4.00). Pin a provider
if cost determinism matters (Wave 2).

## Open items to confirm at Wave 2/3 spec time (when actually wired)
- Exact Gemini "flash" slug for the budget lineup — `gemini-3.1-flash-lite` vs. a
  full `gemini-3.1-flash` if one appears. Only matters for the Wave 3 budget lineup.
- Kimi provider pin + whether `structured_outputs` is supported on the chosen route
  (needed for the Exacto/structured-output path in Wave 2).
- Live per-generation cost via `/api/v1/generation` (Wave 2 cost_meter ground truth).

Wave 1 uses these only as **fixture values** in schema examples — no live calls.

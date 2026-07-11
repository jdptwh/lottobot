# Wave 3 notes — re-verified 2026-07-07

Re-verification per the standing rule (same-day as Waves 1-2 baseline; still current).

## Lineup slugs/prices (unchanged, still live)
- Synthesizer/arbiter: `anthropic/claude-opus-4.8` — $5/M in, $25/M out; prompt
  cache-read $0.5/M (90% off) on Anthropic-direct. `structured_outputs` supported on
  Anthropic-direct + Bedrock routes; `response_format` on all routes.
- Cheap test experts: `deepseek/deepseek-v4-pro` ($0.435/$0.87),
  `deepseek/deepseek-v4-flash` ($0.09/$0.18), `google/gemini-3.1-flash-lite`
  ($0.25/$1.50), `openai/gpt-5.5` ($5/$30), `moonshotai/kimi-k2.6` (~$0.95/$4.0).

## Structured outputs (for parseable expert/synth JSON)
- `response_format:{type:"json_schema", json_schema:{name, strict:true, schema}}` is
  the universal path (works on deepseek-v4-pro DeepSeek-direct, opus-4.8 all routes).
- Strict `structured_outputs` param is route-dependent (deepseek-v4-pro: Alibaba /
  Fireworks / DeepInfra / Together / etc.; opus-4.8: Anthropic + Bedrock). Pair with
  `provider:{require_parameters:true}` only if strict enforcement is required, else
  accept `response_format` on the cheapest route and validate the returned JSON locally.
- Wave 3's gate is MOCKED — structured-output behavior is asserted on the request
  shape and on local JSON validation, not via live calls.

## Concurrency decision input (for the planner)
Wave 2's `call_model` is synchronous. Parallel fan-out of 2-3 experts is I/O-bound
(HTTP wait), so stdlib `concurrent.futures.ThreadPoolExecutor` over the existing sync
`call_model` gives real parallelism (urllib releases the GIL during socket I/O) with
ZERO new dependency. Recommendation: threads, not asyncio+httpx — keeps the satellite
stdlib-only through Wave 3. The injectable-transport seam already makes calls mockable.

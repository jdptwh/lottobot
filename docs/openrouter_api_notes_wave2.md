# OpenRouter API surface — verified 2026-07-07 (for Wave 2)

Facts the Wave 2 adapters/cost_meter/safe_retry depend on. Verified from
openrouter.ai/docs on 2026-07-07. Model IDs/prices unchanged from
`openrouter_models_verified_2026-07-07.md` (same-day verification).

## Endpoint & auth
- Base URL `https://openrouter.ai/api/v1`; chat at `POST /chat/completions`
  (OpenAI-compatible). `Authorization: Bearer <OPENROUTER_API_KEY>`.
- Optional ranking headers `HTTP-Referer`, `X-Title` (harmless to include).
- **Key handling:** store OUTSIDE the repo; read from env `OPENROUTER_API_KEY`.
  Never `ANTHROPIC_API_KEY` in the lead env (V5_PLAN Key Finding 5 footgun). The
  panel is a separate process; OpenRouter key only.

## Cost ground truth (cost_meter)
- Add `"usage": {"include": true}` to the request body → the response `usage`
  object carries the authoritative numbers, no extra call:
  `usage.cost` (USD charged), `usage.prompt_tokens`, `usage.completion_tokens`,
  `usage.total_tokens`, `usage.prompt_tokens_details.cached_tokens`,
  `usage.cost_details.upstream_inference_cost` (BYOK only).
- cost_meter sums `usage.cost` across experts + synthesizer; compares to
  `PANEL_MAX_COST_USD`. Use `usage.cost` as truth, not a hand price×token calc
  (prices drift; caching changes effective cost). Fall back to token×list-price
  ONLY if `usage.cost` is absent.
- Alternative async path: note response `id`, GET `/api/v1/generation?id=...`.
  Not needed if inline usage is on; keep as a fallback for audits.

## Structured outputs (deterministic verdict parsing)
- `response_format: {type:"json_schema", json_schema:{name, strict:true, schema:{...}}}`.
- Pair with `provider:{require_parameters:true}` so OpenRouter only routes to
  providers that actually support the schema (else params are silently dropped).
- Supported by select models/providers — check per-model support; on the chosen
  route confirm `structured_outputs` in supported_parameters (seen for
  deepseek-v4-pro, gpt-5.5, kimi on several providers in the models dump).

## Provider routing / determinism
- `provider` object: `order` (try in listed order), `allow_fallbacks` (bool),
  `require_parameters`, `sort` (price|throughput|latency), `ignore`, `quantizations`.
- To pin Kimi to a specific provider for cost determinism: `provider:{order:["Io Net"],
  allow_fallbacks:false}`. Otherwise price-weighted load balancing picks the route.
- Tool requests auto-filter to tool-capable providers. (Plan's "Exacto" = highest
  tool-call-accuracy routing; confirm the exact opt-in flag at implementation —
  not load-bearing for the Wave 2 mocked gate.)

## Error / retry semantics (safe_retry)
- Error body shape: `{error:{code, message, metadata?}}`. HTTP status mirrors code
  for request errors.
- **Retryable (transient):** 408 timeout, 429 rate-limit, 502 model down, 503 no
  provider meets routing. Also "no content generated" (cold start) → retry.
- **NOT retryable (terminal):** 400 bad request, 401 invalid creds, 402 out of
  credits, 403 moderation-flagged. safe_retry must NOT loop on these.
- **Trap:** an error can arrive as HTTP 200 with `error` in the body / an SSE
  event (mid-generation failure). safe_retry must inspect the parsed body for
  `error`, not just the HTTP status.
- Panel calls are read-only/stateless → retries are always side-effect-safe
  (adopt OpenRouter runAgentWithRetry semantics; exponential backoff on the
  transient set only).

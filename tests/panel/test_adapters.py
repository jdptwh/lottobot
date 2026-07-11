"""Wave 2 — adapter unit tests. All network is mocked via an injected transport."""
import json

import pytest

from panel.adapters import call_model, ModelResult
from panel.errors import (
    MissingAPIKeyError,
    TerminalProviderError,
    TransientProviderError,
)

KEY = "sk-or-test-key"


def make_transport(status, body, record=None):
    """Return a transport callable that yields (status, body_bytes) and, if a
    `record` dict is passed, captures the outgoing url/data/headers."""
    body_bytes = json.dumps(body).encode() if not isinstance(body, (bytes, bytearray)) else body

    def transport(url, data, headers):
        if record is not None:
            record["url"] = url
            record["headers"] = headers
            record["body"] = json.loads(data)
        return status, body_bytes

    return transport


def success_body(content="ok", cost=0.0123, pt=500, ct=120):
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"cost": cost, "prompt_tokens": pt, "completion_tokens": ct},
    }


# ---- request shaping (criterion 2) -------------------------------------------

def test_request_always_includes_usage_accounting():
    rec = {}
    call_model("openai/gpt-5.5", [{"role": "user", "content": "hi"}],
               api_key=KEY, transport=make_transport(200, success_body(), rec))
    assert rec["body"]["usage"] == {"include": True}
    assert rec["body"]["model"] == "openai/gpt-5.5"


def test_optional_params_included_only_when_passed():
    rec = {}
    rf = {"type": "json_schema", "json_schema": {"name": "v", "strict": True, "schema": {}}}
    prov = {"require_parameters": True, "order": ["DeepSeek"]}
    call_model("deepseek/deepseek-v4-pro", [{"role": "user", "content": "hi"}],
               response_format=rf, provider=prov, max_tokens=64,
               api_key=KEY, transport=make_transport(200, success_body(), rec))
    assert rec["body"]["response_format"] == rf
    assert rec["body"]["provider"] == prov
    assert rec["body"]["max_tokens"] == 64


def test_optional_params_absent_by_default():
    rec = {}
    call_model("openai/gpt-5.5", [{"role": "user", "content": "hi"}],
               api_key=KEY, transport=make_transport(200, success_body(), rec))
    for k in ("response_format", "provider", "max_tokens"):
        assert k not in rec["body"]


def test_auth_and_content_type_headers():
    rec = {}
    call_model("openai/gpt-5.5", [{"role": "user", "content": "hi"}],
               api_key=KEY, transport=make_transport(200, success_body(), rec))
    assert rec["headers"]["Authorization"] == f"Bearer {KEY}"
    assert rec["headers"]["Content-Type"] == "application/json"


# ---- key handling (criterion 3) ----------------------------------------------

def test_missing_key_raises_before_transport(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def exploding_transport(url, data, headers):
        raise AssertionError("transport must not be called without a key")

    with pytest.raises(MissingAPIKeyError):
        call_model("openai/gpt-5.5", [{"role": "user", "content": "hi"}],
                   transport=exploding_transport)


def test_key_read_from_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-env")
    rec = {}
    call_model("openai/gpt-5.5", [{"role": "user", "content": "hi"}],
               transport=make_transport(200, success_body(), rec))
    assert rec["headers"]["Authorization"] == "Bearer sk-env"


# ---- 200-with-error trap (criterion 4) ---------------------------------------

def test_http_200_with_transient_error_body():
    tx = make_transport(200, {"error": {"code": 429, "message": "rate"}})
    with pytest.raises(TransientProviderError) as ei:
        call_model("openai/gpt-5.5", [{"role": "user", "content": "hi"}], api_key=KEY, transport=tx)
    assert ei.value.code == 429


def test_http_200_with_terminal_error_body():
    tx = make_transport(200, {"error": {"code": 400, "message": "bad"}})
    with pytest.raises(TerminalProviderError):
        call_model("openai/gpt-5.5", [{"role": "user", "content": "hi"}], api_key=KEY, transport=tx)


# ---- classification table (criterion 5) --------------------------------------

@pytest.mark.parametrize("code", [408, 429, 502, 503])
def test_transient_codes(code):
    tx = make_transport(code, {"error": {"code": code, "message": "x"}})
    with pytest.raises(TransientProviderError):
        call_model("m", [{"role": "user", "content": "hi"}], api_key=KEY, transport=tx)


@pytest.mark.parametrize("code", [400, 401, 402, 403, 418])
def test_terminal_and_unknown_codes(code):
    tx = make_transport(code, {"error": {"code": code, "message": "x"}})
    with pytest.raises(TerminalProviderError):
        call_model("m", [{"role": "user", "content": "hi"}], api_key=KEY, transport=tx)


def test_no_content_is_transient():
    tx = make_transport(200, {"choices": [], "usage": {}})
    with pytest.raises(TransientProviderError):
        call_model("m", [{"role": "user", "content": "hi"}], api_key=KEY, transport=tx)


def test_non_2xx_without_error_body_is_classified():
    tx = make_transport(503, {})
    with pytest.raises(TransientProviderError):
        call_model("m", [{"role": "user", "content": "hi"}], api_key=KEY, transport=tx)


# ---- success parsing (criterion 6) -------------------------------------------

def test_success_parsed_into_model_result():
    tx = make_transport(200, success_body(content="hello", cost=0.02, pt=300, ct=40))
    r = call_model("anthropic/claude-opus-4.8", [{"role": "user", "content": "hi"}],
                   api_key=KEY, transport=tx)
    assert isinstance(r, ModelResult)
    assert r.content == "hello"
    assert r.tokens_in == 300 and r.tokens_out == 40
    assert r.cost_usd == 0.02
    assert r.model == "anthropic/claude-opus-4.8"


def test_cost_none_when_usage_cost_absent():
    body = {"choices": [{"message": {"content": "x"}}], "usage": {"prompt_tokens": 5, "completion_tokens": 2}}
    r = call_model("m", [{"role": "user", "content": "hi"}], api_key=KEY, transport=make_transport(200, body))
    assert r.cost_usd is None
    assert r.tokens_in == 5 and r.tokens_out == 2


def test_stringified_error_code_still_classified():
    # Robustness: some providers may stringify error.code. A "429" string must
    # still classify transient, not fall through to terminal.
    tx = make_transport(200, {"error": {"code": "429", "message": "rate"}})
    with pytest.raises(TransientProviderError):
        call_model("m", [{"role": "user", "content": "hi"}], api_key=KEY, transport=tx)

"""Importable Wave 3 test fakes/builders (imported by orchestrator test modules).

Kept as a plain module (not conftest) so tests can `import orch_fakes`; the repo's
root conftest.py puts tests/panel on sys.path. The `lint_exit` pytest fixture lives
in tests/panel/conftest.py.
"""
import json

from panel.adapters import ModelResult


class FakeCallModel:
    """Drop-in for panel.adapters.call_model, keyed by model slug. Each entry:
      - (content_obj, cost_usd): a ModelResult (content JSON-encoded if a dict)
      - an Exception instance: raised on every call
      - a list of the above: consumed one per call (retry sequences)
    Records every call in .calls.
    """

    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls = []
        self._seq_idx = {}

    def __call__(self, model, messages, *, response_format=None, provider=None,
                 max_tokens=None, api_key=None, transport=None, extra_headers=None):
        self.calls.append({"model": model, "messages": messages,
                           "response_format": response_format, "max_tokens": max_tokens})
        spec = self.responses[model]
        if isinstance(spec, list):
            i = self._seq_idx.get(model, 0)
            spec = spec[min(i, len(spec) - 1)]
            self._seq_idx[model] = i + 1
        if isinstance(spec, BaseException):
            raise spec
        content_obj, cost = spec
        content = content_obj if isinstance(content_obj, str) else json.dumps(content_obj)
        return ModelResult(model=model, content=content, tokens_in=100,
                           tokens_out=50, cost_usd=cost, raw={})

    def models_called(self):
        return [c["model"] for c in self.calls]


def expert_plan(summary="s", recommendation="r", plan="p", confidence=0.8, findings=None):
    return {"summary": summary, "recommendation": recommendation, "plan": plan,
            "confidence": confidence, "findings": findings or []}


def expert_review(summary="s", confidence=0.8, findings=None):
    return {"summary": summary, "confidence": confidence, "findings": findings or []}


def synth(artifact="merged plan", consensus=None, contradictions=None, unique=None,
          blind_spots=None, findings=None):
    return {"artifact": artifact, "consensus_points": consensus or [],
            "contradictions": contradictions or [], "unique_insights": unique or [],
            "blind_spots": blind_spots or [], "rationale": "merged", "findings": findings or []}


def arbiter(rulings):
    return {"rulings": rulings}


def assert_valid_panel_verdict(v):
    """Dependency-free check of the panel_verdict invariants the JSON schema
    enforces but verdict_lint.py does not (confidence bounds, contradiction shape,
    severity/arbiter enums). Pins the Wave 3 sanitization guards."""
    assert v["source"] == "panel"
    assert v["gate"] in ("plan", "review")
    assert v["verdict"] in ("PASS", "FAIL", "REVISE")
    assert isinstance(v["cost_cap_breached"], bool)
    assert isinstance(v["cost_usd_total"], (int, float)) and not isinstance(v["cost_usd_total"], bool)
    assert len(v["expert_opinions"]) >= 1, "schema minItems=1"
    for e in v["expert_opinions"]:
        assert isinstance(e["model"], str) and isinstance(e["summary"], str)
        assert isinstance(e["confidence"], (int, float)) and not isinstance(e["confidence"], bool)
        assert 0.0 <= e["confidence"] <= 1.0, f"confidence out of range: {e['confidence']}"
    syn = v["synthesis"]
    assert isinstance(syn["synthesizer"], str)
    assert syn["artifact"] is None or isinstance(syn["artifact"], str)
    for f in syn.get("findings", []):
        assert f["severity"] in ("critical", "major", "minor"), f"bad severity {f['severity']}"
        assert f.get("arbiter_ruling") in ("upheld", "rejected", None)
    for c in v["disagreement_summary"].get("contradictions", []):
        assert isinstance(c, dict) and "topic" in c and "positions" in c
        for p in c["positions"]:
            assert isinstance(p, dict)

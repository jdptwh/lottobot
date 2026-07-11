"""Wave 5 — render: fixture fields present, XSS escaped, config fields present."""
import json

from panel.dashboard.config_writer import EDITABLE_KEYS
from panel.dashboard.render import render_index


def test_renders_verdict_fields(sample_verdict):
    v = dict(sample_verdict, present=True)
    html = render_index(v, {"total_usd": 0.9, "count": 1, "latest": None}, {})
    assert "Latest verdict" in html
    assert "badge PASS" in html
    assert sample_verdict["task_id"] in html
    for e in sample_verdict["expert_opinions"]:
        assert e["model"] in html


def test_xss_escaped():
    v = {"present": True, "gate": "plan", "task_id": "t", "verdict": "PASS",
         "cost_usd_total": 0, "cost_cap_breached": False,
         "expert_opinions": [{"model": "m", "role": "expert", "confidence": 0.5,
                              "summary": "<script>alert(1)</script>"}],
         "synthesis": {"synthesizer": "s", "artifact": "<script>bad</script>", "findings": []},
         "disagreement_summary": {}}
    html = render_index(v, {"total_usd": 0, "count": 0, "latest": None}, {})
    assert "<script>alert(1)</script>" not in html
    assert "<script>bad</script>" not in html
    assert "&lt;script&gt;" in html


def test_config_editor_shows_all_editable_keys():
    editable = {k: "x" for k in EDITABLE_KEYS}
    html = render_index({"present": False}, {"total_usd": 0, "count": 0, "latest": None}, editable)
    for k in EDITABLE_KEYS:
        assert k in html
    # PANEL_ENABLED carries the paid-calls warning
    assert "arms real, paid OpenRouter calls" in html   # paid-calls warning (new UI copy)
    # no external resources
    assert "http://" not in html and "https://" not in html


def test_absent_verdict_no_crash():
    html = render_index({"present": False}, {"total_usd": 0, "count": 0, "latest": None}, {})
    assert "No panel_verdict.json yet" in html

"""Wave 5 — cost log: idempotent observe, tally sums distinct runs."""
from panel.dashboard import costlog


def v(task_id, cost, verdict="PASS"):
    return {"task_id": task_id, "gate": "plan", "verdict": verdict,
            "cost_usd_total": cost, "cost_cap_breached": False}


def test_observe_appends_new_and_dedups(cost_log):
    assert costlog.observe(str(cost_log), v("t1", 0.9)) is True
    assert costlog.observe(str(cost_log), v("t1", 0.9)) is False   # same fingerprint
    assert costlog.observe(str(cost_log), v("t2", 0.5)) is True
    t = costlog.tally(str(cost_log))
    assert t["count"] == 2
    assert abs(t["total_usd"] - 1.4) < 1e-9
    assert t["latest"]["task_id"] == "t2"


def test_same_task_different_cost_is_new(cost_log):
    costlog.observe(str(cost_log), v("t1", 0.9))
    assert costlog.observe(str(cost_log), v("t1", 1.1)) is True     # cost changed -> new run
    assert costlog.tally(str(cost_log))["count"] == 2


def test_tally_missing_file():
    t = costlog.tally("/no/such/cost.jsonl")
    assert t == {"total_usd": 0.0, "count": 0, "latest": None, "entries": []}


def test_observe_ignores_non_verdict(cost_log):
    assert costlog.observe(str(cost_log), {"present": False}) is False
    assert costlog.tally(str(cost_log))["count"] == 0

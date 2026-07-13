"""tests/workflow/test_daily_workflow.py — M5 workflow assertions (AC-8).

Parses .github/workflows/daily.yml with yaml.safe_load and asserts the
hard rules pinned by the spec (trigger set, cron, permissions, concurrency,
python-version, step execution, commit identity, and no force-push anywhere).

Implementation note: PyYAML loads the on: key as boolean True (YAML 1.1);
resolve triggers via doc.get("on", doc.get(True)).

The .github/workflows/ directory is this project's own artifact, not part of
the installable harness, and is not copied into the nested self-test directory
(scripts/harness.manifest.json's copy_dirs is .claude/*, panel, tests, docs
— no ".github").
"""
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "daily.yml"

# Skip all tests in this module if the workflow file doesn't exist (harness self-test)
if not WORKFLOW_PATH.exists():
    pytest.skip(
        ".github/workflows/daily.yml is this project's own artifact, not part of the installable harness",
        allow_module_level=True,
    )


@pytest.fixture(scope="module")
def workflow_doc():
    """Load and parse the daily workflow YAML."""
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    return yaml.safe_load(text)


class TestWorkflowTriggers:
    """AC-8: trigger set == exactly {"schedule", "workflow_dispatch"}."""

    def test_trigger_set_exact(self, workflow_doc):
        # PyYAML 1.1 loads 'on:' key as boolean True
        on_obj = workflow_doc.get("on", workflow_doc.get(True))
        assert on_obj is not None, "on: key not found in workflow"
        assert set(on_obj.keys()) == {"schedule", "workflow_dispatch"}

    def test_no_on_push_trigger(self, workflow_doc):
        """Implied by trigger-set assertion: on: push must not be present."""
        on_obj = workflow_doc.get("on", workflow_doc.get(True))
        assert "push" not in on_obj


class TestWorkflowCron:
    """AC-8: cron == "30 10 * * *"."""

    def test_cron_schedule(self, workflow_doc):
        on_obj = workflow_doc.get("on", workflow_doc.get(True))
        schedule = on_obj.get("schedule")
        assert schedule is not None
        assert isinstance(schedule, list)
        assert len(schedule) > 0
        # First schedule entry should have the cron
        first_schedule = schedule[0]
        assert first_schedule.get("cron") == "30 10 * * *"


class TestWorkflowPermissions:
    """AC-8: permissions == exactly {contents: write, issues: write}."""

    def test_permissions_exact(self, workflow_doc):
        perms = workflow_doc.get("permissions", {})
        assert perms == {"contents": "write", "issues": "write"}


class TestWorkflowConcurrency:
    """AC-8: concurrency group present and cancel-in-progress is False."""

    def test_concurrency_group_present(self, workflow_doc):
        conc = workflow_doc.get("concurrency")
        assert conc is not None, "concurrency section not found"
        assert conc.get("group") == "daily-pipeline"

    def test_cancel_in_progress_false(self, workflow_doc):
        conc = workflow_doc.get("concurrency")
        assert conc.get("cancel-in-progress") is False


class TestWorkflowPythonVersion:
    """AC-8: python-version == "3.11"."""

    def test_python_version(self, workflow_doc):
        jobs = workflow_doc.get("jobs", {})
        run_job = jobs.get("run")
        assert run_job is not None
        steps = run_job.get("steps", [])

        # Find the setup-python step
        setup_py_step = None
        for step in steps:
            if "uses" in step and "setup-python" in step["uses"]:
                setup_py_step = step
                break

        assert setup_py_step is not None, "setup-python step not found"
        with_dict = setup_py_step.get("with", {})
        assert with_dict.get("python-version") == "3.11"


class TestWorkflowPipelineStep:
    """AC-8: the pipeline step runs 'python -m scraper.run_daily --live'."""

    def test_pipeline_step_command(self, workflow_doc):
        jobs = workflow_doc.get("jobs", {})
        run_job = jobs.get("run")
        steps = run_job.get("steps", [])

        # Find the "Run daily pipeline" step
        pipeline_step = None
        for step in steps:
            if step.get("name") == "Run daily pipeline (all gates enforced; no write on failure)":
                pipeline_step = step
                break

        assert pipeline_step is not None, "Run daily pipeline step not found"
        assert pipeline_step.get("run") == "python -m scraper.run_daily --live"


class TestWorkflowCommitStep:
    """AC-8: commit step contains literal 'git add data/latest.json data/history/'
    and a plain 'git push'."""

    def test_commit_step_exists(self, workflow_doc):
        jobs = workflow_doc.get("jobs", {})
        run_job = jobs.get("run")
        steps = run_job.get("steps", [])

        # Find the commit step
        commit_step = None
        for step in steps:
            if step.get("name") == "Commit and push snapshot":
                commit_step = step
                break

        assert commit_step is not None, "Commit and push snapshot step not found"

    def test_commit_step_has_git_add(self, workflow_doc):
        jobs = workflow_doc.get("jobs", {})
        run_job = jobs.get("run")
        steps = run_job.get("steps", [])

        commit_step = None
        for step in steps:
            if step.get("name") == "Commit and push snapshot":
                commit_step = step
                break

        run_script = commit_step.get("run", "")
        assert "git add data/latest.json data/history/" in run_script

    def test_commit_step_has_plain_git_push(self, workflow_doc):
        jobs = workflow_doc.get("jobs", {})
        run_job = jobs.get("run")
        steps = run_job.get("steps", [])

        commit_step = None
        for step in steps:
            if step.get("name") == "Commit and push snapshot":
                commit_step = step
                break

        run_script = commit_step.get("run", "")
        assert "git push" in run_script


class TestWorkflowNoForcePush:
    """AC-8: the strings '--force', '-f origin', and 'push -f' appear nowhere."""

    def test_no_force_flag_in_workflow(self, workflow_doc):
        # Reconstruct the YAML string to search for all forbidden patterns
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "--force" not in text
        assert "-f origin" not in text
        assert "push -f" not in text


class TestWorkflowFailureStep:
    """AC-8: failure step has if: failure(), references label daily-run-failure,
    and gh issue list dedup appears before gh issue create."""

    def test_failure_step_exists(self, workflow_doc):
        jobs = workflow_doc.get("jobs", {})
        run_job = jobs.get("run")
        steps = run_job.get("steps", [])

        failure_step = None
        for step in steps:
            if step.get("name") == "Open failure issue (deduplicated per day)":
                failure_step = step
                break

        assert failure_step is not None, "Open failure issue step not found"

    def test_failure_step_if_condition(self, workflow_doc):
        jobs = workflow_doc.get("jobs", {})
        run_job = jobs.get("run")
        steps = run_job.get("steps", [])

        failure_step = None
        for step in steps:
            if step.get("name") == "Open failure issue (deduplicated per day)":
                failure_step = step
                break

        assert failure_step.get("if") == "failure()"

    def test_failure_step_label_reference(self, workflow_doc):
        jobs = workflow_doc.get("jobs", {})
        run_job = jobs.get("run")
        steps = run_job.get("steps", [])

        failure_step = None
        for step in steps:
            if step.get("name") == "Open failure issue (deduplicated per day)":
                failure_step = step
                break

        run_script = failure_step.get("run", "")
        assert "daily-run-failure" in run_script

    def test_gh_issue_list_before_gh_issue_create(self, workflow_doc):
        jobs = workflow_doc.get("jobs", {})
        run_job = jobs.get("run")
        steps = run_job.get("steps", [])

        failure_step = None
        for step in steps:
            if step.get("name") == "Open failure issue (deduplicated per day)":
                failure_step = step
                break

        run_script = failure_step.get("run", "")
        # Both commands must be present
        assert "gh issue list" in run_script
        assert "gh issue create" in run_script
        # The list command must come before create
        list_pos = run_script.find("gh issue list")
        create_pos = run_script.find("gh issue create")
        assert list_pos < create_pos, "gh issue list must appear before gh issue create"


class TestWorkflowBotIdentity:
    """AC-8: commit identity has the two pinned github-actions[bot] strings."""

    def test_bot_name_and_email(self, workflow_doc):
        jobs = workflow_doc.get("jobs", {})
        run_job = jobs.get("run")
        steps = run_job.get("steps", [])

        commit_step = None
        for step in steps:
            if step.get("name") == "Commit and push snapshot":
                commit_step = step
                break

        run_script = commit_step.get("run", "")
        # Both identity strings must be present
        assert 'git config user.name "github-actions[bot]"' in run_script
        assert "41898282+github-actions[bot]@users.noreply.github.com" in run_script

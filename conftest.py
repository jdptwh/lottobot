# Ensures the repo root is importable (so `import panel.*` works) even if a
# pytest config option is ever lost. Belt-and-suspenders alongside pyproject's
# pythonpath = ["."].
import getpass
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))


def _temproot_is_poisoned():
    """Windows: a pytest run from an ELEVATED shell can leave a pytest-current
    symlink in %TEMP%\\pytest-of-<user> that a normal shell can neither replace
    nor delete (WinError 5) — after which EVERY later pytest run (including the
    gate hook) dies in tmp_path_factory. Detect that exact state."""
    if os.name != "nt" or os.environ.get("PYTEST_DEBUG_TEMPROOT"):
        return False
    try:
        link = os.path.join(tempfile.gettempdir(),
                            f"pytest-of-{getpass.getuser()}", "pytest-current")
    except Exception:
        return False
    if not os.path.lexists(link):
        return False
    probe = link + ".probe"
    try:  # can we replace it, as pytest will try to?
        os.replace(link, probe)
        os.replace(probe, link)
        return False
    except OSError:
        return True


if _temproot_is_poisoned():
    _alt = os.path.join(tempfile.gettempdir(), "pytest-temproot-unelevated")
    os.makedirs(_alt, exist_ok=True)
    os.environ["PYTEST_DEBUG_TEMPROOT"] = _alt

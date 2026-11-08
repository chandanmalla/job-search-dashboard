"""Portable locations for the dashboard repo and the canonical job-tracker state.

JT_DIR selects the canonical directory. The default is state/job-tracker inside
this repo when it already holds tracked_jobs.json, otherwise the historical
Windows path if that directory exists. Nothing here reads secrets.
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
_WIN_JT = Path(r"C:\Users\chand\Downloads\Job Search\job-tracker")
_WIN_PY = _WIN_JT / "python-embed" / "python.exe"
_WIN_GIT = Path(r"C:\Users\chand\Downloads\Job Search\git-portable\cmd\git.exe")


def job_tracker_dir() -> Path:
    env = os.environ.get("JT_DIR")
    if env:
        return Path(env)
    local = REPO_ROOT / "state" / "job-tracker"
    if (local / "tracked_jobs.json").exists():
        return local
    if _WIN_JT.exists():
        return _WIN_JT
    return local


def python_exe() -> str:
    env = os.environ.get("PY_EXE")
    if env:
        return env
    if _WIN_PY.exists():
        return str(_WIN_PY)
    return sys.executable or "python3"


def git_exe() -> str:
    env = os.environ.get("GIT_EXE")
    if env:
        return env
    if _WIN_GIT.exists():
        return str(_WIN_GIT)
    return "git"


def inbox_path() -> Path:
    env = os.environ.get("INBOX_PATH")
    if env:
        return Path(env)
    return REPO_ROOT / "data" / "applied_inbox.json"


def ensure_import_path() -> Path:
    jt = job_tracker_dir()
    jt.mkdir(parents=True, exist_ok=True)
    entry = str(jt)
    if entry not in sys.path:
        sys.path.insert(0, entry)
    scripts = str(SCRIPTS_DIR)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    return jt

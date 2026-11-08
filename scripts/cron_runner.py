"""
Legacy PC orchestrator. The hosted path is scripts/hosted_runner.py.

This file still runs the full PC sequence (Telegram sync, crawl, referral flag,
report/digest, outreach, publish) so the existing machine keeps its behavior
until that scheduled task is disabled. Paths are portable: JT_DIR, PY_EXE and
GIT_EXE override the historical Windows locations.

It does not claim success when a step fails, and it does not use `git add .`
or a rebase strategy that keeps one side of an inbox conflict.
"""

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import git_exe, job_tracker_dir, python_exe
from redact import redact

SCRIPTS_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPTS_DIR.parent
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
CHILD_ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", GIT_TERMINAL_PROMPT="0")
_LOG = None
_FAILED = []


def log(msg, **_kw):
    print(redact(msg), flush=True)
    if _LOG:
        _LOG.write(redact(msg) + "\n")
        _LOG.flush()


def run_step(desc, cmd, cwd=None):
    log(f"\n[cron] === {desc} ===")
    try:
        res = subprocess.run(
            cmd, cwd=cwd or str(PROJECT_DIR), capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=CHILD_ENV, timeout=1800,
        )
    except Exception as exc:
        log(f"[cron] FAILED {desc}: {exc}")
        _FAILED.append(desc)
        return False
    if res.stdout:
        log(res.stdout.strip())
    if res.stderr and res.returncode != 0:
        log(f"[cron] Warning in {desc} (exit {res.returncode}): {res.stderr.strip()}")
    elif res.stderr and "git" in desc.lower():
        log(res.stderr.strip())
    if res.returncode != 0:
        _FAILED.append(desc)
        return False
    return True


def main():
    global _LOG
    py = python_exe()
    git = git_exe()
    jt = job_tracker_dir()
    log_dir = jt / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _LOG = open(log_dir / f"cron_{datetime.now().strftime('%Y%m%d')}.log", "a", encoding="utf-8")
    now_str = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M IST")
    log(f"[cron] Starting alternating 2-hourly job sweep (Top Product Companies) at {now_str}...")

    run_step("0. Git Pull (rebase, autostash)", [git, "pull", "--rebase", "--autostash", "origin", "main"])
    run_step("0b. Processing Website Marks Inbox", [py, str(SCRIPTS_DIR / "process_inbox.py")])
    run_step("1. Syncing Applied Jobs from Telegram", [py, str(SCRIPTS_DIR / "sync_applied_from_telegram.py")])
    run_step("2. Running Alternating Sweep Crawler (Top Product Companies)", [py, str(SCRIPTS_DIR / "sweep_crawler.py")])
    run_step("2a. Auto-flag Best-match Jobs for Referral", [py, str(SCRIPTS_DIR / "auto_referral_needed.py")])
    run_step("2b. Merging Referral Updates", [py, str(SCRIPTS_DIR / "merge_referral_updates.py")])

    found_json = jt / "found_jobs_latest.json"
    if found_json.exists():
        run_step(
            "3. Updating Tracked Database & Sending Telegram Digest",
            [py, str(jt / "generate_report.py"), "--jobs", str(found_json)],
        )
    else:
        log("[cron] SKIPPED 3. Updating Tracked Database: found_jobs_latest.json missing")

    run_step("3b. Auto-flag New Best-match Jobs for Referral", [py, str(SCRIPTS_DIR / "auto_referral_needed.py")])
    run_step("3c. Merging Referral Updates (auto-flagged)", [py, str(SCRIPTS_DIR / "merge_referral_updates.py")])
    run_step("4. Rebuilding Web Dashboard (index.html + data/jobs.json)", [py, str(PROJECT_DIR / "build_site.py")])
    run_step("4b. Refreshing Outreach Queue", [py, str(jt / "outreach_queue.py")])

    publish_paths = [
        "data/applied_inbox.json", "data/jobs.json", "index.html",
    ]
    existing = [path for path in publish_paths if Path(path).exists()]
    run_step("5. Git Add", [git, "add", "--", *existing])
    run_step("6. Git Commit", [git, "commit", "-m", f"Automated 2-hourly sweep update ({now_str})"])
    pulled = run_step("6b. Git Pull before push", [git, "pull", "--rebase", "--autostash", "origin", "main"])
    if not pulled:
        log("[cron] Refusing to push because rebase failed. Remote inbox marks were not overwritten.")
        log(f"[cron] FAILED steps: {_FAILED}")
        return 1
    pushed = run_step("7. Git Push to GitHub Pages", [git, "push", "origin", "main"])
    log(f"[cron] Git push {'succeeded' if pushed else 'FAILED'}.")
    if _FAILED:
        log(f"[cron] Finished with failed steps: {_FAILED}")
        return 1
    log(f"\n[cron] 2-hourly alternating run finished successfully at {now_str}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

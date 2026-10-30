"""
Master 2-Hourly Cron Orchestrator (Top Product Companies Only)
==============================================================
Runs completely unattended every 2 hours:
1. Ingests any /applied or /skip messages sent to Telegram while you were away.
2. Runs the intelligent Sweep Crawler which alternates every run:
   - Run A: Deep-scrapes fresh openings from EXISTING top product companies (Apple, Meta, Google, Microsoft, Databricks, Flipkart, Spotify, etc.)
   - Run B: Probes NEW top product companies, unicorns, and AI labs across Greenhouse, Lever, Ashby, and verified postings.
   - Strictly targets core Data Science & Applied Science roles (~5-yr experience).
   - Strictly EXCLUDES IT services, consultancies, staffing agencies, SWE/engineering, and Amazon subsidiaries.
3. Updates the local database and generates Excel + HTML reports.
4. Sends the consolidated Telegram digest to both subscribed chat IDs.
5. Rebuilds the web dashboard (index.html + data/jobs.json).
6. Commits and pushes updates to GitHub so your live hosted dashboard updates automatically!
"""

import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

SCRIPTS_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPTS_DIR.parent
PY_EXE = Path(r"C:\Users\chand\Downloads\Job Search\job-tracker\python-embed\python.exe")
GIT_EXE = Path(r"C:\Users\chand\Downloads\Job Search\git-portable\cmd\git.exe")
LOG_DIR = Path(r"C:\Users\chand\Downloads\Job Search\job-tracker\logs")
import os
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
CHILD_ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", GIT_TERMINAL_PROMPT="0")
_LOG = None

def log(msg, **_kw):
    print(msg, flush=True)
    if _LOG:
        _LOG.write(msg + "\n"); _LOG.flush()

def run_step(desc, cmd, cwd=None):
    log(f"\n[cron] === {desc} ===")
    try:
        res = subprocess.run(cmd, cwd=cwd or str(PROJECT_DIR), capture_output=True, text=True, encoding="utf-8",
                             errors="replace", env=CHILD_ENV, timeout=1800)
    except Exception as e:
        log(f"[cron] FAILED {desc}: {e}")
        return False
    if res.stdout:
        log(res.stdout.strip())
    if res.stderr and res.returncode != 0:
        log(f"[cron] Warning in {desc} (exit {res.returncode}): {res.stderr.strip()}")
    elif res.stderr and "git" in desc.lower():
        log(res.stderr.strip())
    return res.returncode == 0

def main():
    global _LOG
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _LOG = open(LOG_DIR / f"cron_{datetime.now().strftime('%Y%m%d')}.log", "a", encoding="utf-8")
    now_str = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M IST")
    log(f"[cron] Starting alternating 2-hourly job sweep (Top Product Companies) at {now_str}...", flush=True)

    # 1. Sync applied/skipped commands sent to Telegram
    run_step("1. Syncing Applied Jobs from Telegram", [
        str(PY_EXE), str(SCRIPTS_DIR / "sync_applied_from_telegram.py")
    ])

    # 2. Run alternating sweep crawler (Data Science & Applied Science at top product companies)
    run_step("2. Running Alternating Sweep Crawler (Top Product Companies)", [
        str(PY_EXE), str(SCRIPTS_DIR / "sweep_crawler.py")
    ])

    # 2b. Merge referral updates from the LinkedIn outreach side channel
    run_step("2b. Merging Referral Updates", [
        str(PY_EXE), r"C:\Users\chand\Downloads\Job Search\job-tracker\merge_referral_updates.py"
    ])

    # 3. Run report generator if found_jobs_latest.json exists
    found_json = Path(r"C:\Users\chand\Downloads\Job Search\job-tracker\found_jobs_latest.json")
    if found_json.exists():
        run_step("3. Updating Tracked Database & Sending Telegram Digest", [
            str(PY_EXE), str(Path(r"C:\Users\chand\Downloads\Job Search\job-tracker\generate_report.py")),
            "--jobs", str(found_json)
        ])

    # 4. Rebuild web dashboard (pre-seeds applied state into index.html)
    run_step("4. Rebuilding Web Dashboard (index.html + data/jobs.json)", [
        str(PY_EXE), str(PROJECT_DIR / "build_site.py")
    ])

    # 4b. Refresh outreach queue
    run_step("4b. Refreshing Outreach Queue", [
        str(PY_EXE), r"C:\Users\chand\Downloads\Job Search\job-tracker\outreach_queue.py"
    ])

    # 5. Push updates to GitHub Pages
    run_step("5. Git Add", [str(GIT_EXE), "add", "."])
    commit_msg = f"Automated 2-hourly sweep update ({now_str})"
    run_step("6. Git Commit", [str(GIT_EXE), "commit", "-m", commit_msg])
    ok = run_step("7. Git Push to GitHub Pages", [str(GIT_EXE), "push", "origin", "main"])
    log(f"[cron] Git push {'succeeded' if ok else 'FAILED'}.")

    log(f"\n[cron] 2-hourly alternating run finished successfully at {now_str}.", flush=True)


if __name__ == "__main__":
    main()

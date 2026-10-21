"""
Master 3-Hourly Cron Orchestrator
==================================
Runs completely unattended every 3 hours:
1. Ingests any /applied or /skip messages sent to Telegram while you were away.
2. Checks for new verified-open ML/DS roles (or consumes newly scraped JSON).
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

def run_step(desc, cmd, cwd=None):
    print(f"\n[cron] === {desc} ===", flush=True)
    res = subprocess.run(cmd, cwd=cwd or str(PROJECT_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.stdout:
        print(res.stdout.strip(), flush=True)
    if res.stderr and res.returncode != 0:
        print(f"[cron] Warning in {desc}: {res.stderr.strip()}", flush=True)
    return res.returncode == 0

def main():
    now_str = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M IST")
    print(f"[cron] Starting 3-hourly job sweep at {now_str}...", flush=True)

    # 1. Sync applied/skipped commands sent to Telegram
    run_step("1. Syncing Applied Jobs from Telegram", [
        str(PY_EXE), str(SCRIPTS_DIR / "sync_applied_from_telegram.py")
    ])

    # 2. Run report generator if found_jobs_latest.json exists
    found_json = Path(r"C:\Users\chand\Downloads\Job Search\job-tracker\found_jobs_latest.json")
    if found_json.exists():
        run_step("2. Updating Tracked Database & Sending Telegram Digest", [
            str(PY_EXE), str(Path(r"C:\Users\chand\Downloads\Job Search\job-tracker\generate_report.py")),
            "--jobs", str(found_json)
        ])

    # 3. Rebuild web dashboard (pre-seeds applied state into index.html)
    run_step("3. Rebuilding Web Dashboard (index.html + data/jobs.json)", [
        str(PY_EXE), str(PROJECT_DIR / "build_site.py")
    ])

    # 4. Push updates to GitHub Pages
    run_step("4. Git Add", [str(GIT_EXE), "add", "."])
    commit_msg = f"Automated 3-hourly sweep update ({now_str})"
    run_step("5. Git Commit", [str(GIT_EXE), "commit", "-m", commit_msg])
    run_step("6. Git Push to GitHub Pages", [str(GIT_EXE), "push", "origin", "main"])

    print(f"\n[cron] 3-hourly run finished successfully at {now_str}.", flush=True)

if __name__ == "__main__":
    main()

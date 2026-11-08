"""Hosted pipeline entrypoint.

applied-sync records website marks, merges them, and rebuilds the dashboard.
It does not crawl, flag referrals, read Telegram, send Telegram, or refresh outreach.

crawl is separate. Telegram and outreach stay off unless the matching flag is passed.
preflight only reports missing canonical files and does not write the dashboard.

Publishing is one git commit of an explicit path list after every step succeeds.
A failed step commits nothing.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from backup_state import backup_state
from paths import REPO_ROOT, SCRIPTS_DIR, job_tracker_dir, python_exe
from preflight import preflight_report
from publish_guard import restore_if_unsafe
from redact import redact

PUBLISH_PATHS = [
    "data/applied_inbox.json",
    "data/jobs.json",
    "index.html",
    "state/health.json",
    "state/job-tracker",
]


def commands(mode: str, *, notifications: bool = False, telegram_sync: bool = False, outreach: bool = False):
    if mode == "applied-sync":
        return ["process_inbox.py", "merge_referral_updates.py", "build_site.py"]
    if mode == "crawl":
        steps = ["sweep_crawler.py", "auto_referral_needed.py", "merge_referral_updates.py"]
        if telegram_sync:
            steps.append("sync_applied_from_telegram.py")
        report = ["generate_report.py", "--jobs", "<found_jobs_latest.json>"]
        if not notifications:
            report.append("--no-telegram")
        steps.append(" ".join(report))
        steps.extend(["auto_referral_needed.py", "merge_referral_updates.py", "build_site.py"])
        if outreach:
            steps.append("outreach_queue.py")
        return steps
    if mode == "preflight":
        return []
    raise ValueError(mode)


def _skipped_side_effects(mode: str, *, notifications: bool, telegram_sync: bool, outreach: bool):
    steps = []
    if mode == "applied-sync":
        steps.append({"name": "sweep_crawler", "status": "skipped", "detail": "applied-sync does not crawl"})
        steps.append({"name": "auto_referral_needed", "status": "skipped", "detail": "applied-sync does not flag referrals"})
        steps.append({"name": "generate_report", "status": "skipped", "detail": "applied-sync does not ingest crawl results"})
        steps.append({"name": "telegram", "status": "skipped", "detail": "applied-sync does not send Telegram"})
        steps.append({"name": "telegram_sync", "status": "skipped", "detail": "applied-sync does not read Telegram"})
        steps.append({"name": "outreach", "status": "skipped", "detail": "applied-sync does not refresh outreach"})
        return steps
    if not telegram_sync:
        steps.append({"name": "telegram_sync", "status": "skipped", "detail": "telegram sync off"})
    if not notifications:
        steps.append({"name": "telegram", "status": "skipped", "detail": "notifications off"})
    if not outreach:
        steps.append({"name": "outreach", "status": "skipped", "detail": "outreach off"})
    return steps


def _run_py(script: Path, args, env):
    result = subprocess.run(
        [python_exe(), str(script), *args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    detail = redact(((result.stdout or "") + "\n" + (result.stderr or "")).strip())
    return result.returncode, detail[-2000:]


def _child_env():
    env = dict(os.environ)
    env["JT_DIR"] = str(job_tracker_dir())
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["HOSTED_STRICT_BUILD"] = "1"
    env.pop("ENABLE_NOTIFICATIONS", None)
    return env


def _guarded_build(env, *, allow_needed: bool, allow_new_jobs: bool, referred_ids=()):
    index = REPO_ROOT / "index.html"
    jobs = REPO_ROOT / "data" / "jobs.json"
    old_html = index.read_text(encoding="utf-8")
    old_jobs = jobs.read_text(encoding="utf-8") if jobs.exists() else "[]"
    code, detail = _run_py(REPO_ROOT / "build_site.py", [], env)
    if code != 0:
        if index.exists():
            index.write_text(old_html, encoding="utf-8")
        if jobs.exists() or old_jobs:
            jobs.write_text(old_jobs, encoding="utf-8")
        return False, f"build_site exit {code}: {detail}"
    errors = restore_if_unsafe(
        index, jobs, old_html, old_jobs,
        allow_needed=allow_needed, allow_new_jobs=allow_new_jobs, referred_ids=referred_ids,
    )
    if errors:
        return False, "publish guard restored previous dashboard: " + "; ".join(errors)
    return True, "dashboard rebuilt"


def execute(mode: str, *, notifications: bool = False, telegram_sync: bool = False, outreach: bool = False) -> dict:
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = {
        "mode": mode,
        "ok": False,
        "started_at": started,
        "finished_at": None,
        "missing_files": [],
        "unresolved_imports": [],
        "steps": [],
    }
    if mode == "applied-sync" and (notifications or telegram_sync or outreach):
        report["steps"].append({
            "name": "side_effects",
            "status": "failed",
            "detail": "applied-sync refuses notifications, telegram sync, and outreach",
        })
        report["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return report
    check = preflight_report(
        job_tracker_dir(),
        "crawl" if mode == "preflight" else mode,
        telegram_sync=telegram_sync,
        scripts_dir=SCRIPTS_DIR,
    )
    report["missing_files"] = check["missing_files"]
    report["unresolved_imports"] = check["unresolved_imports"]
    report["steps"].extend(_skipped_side_effects(
        mode, notifications=notifications, telegram_sync=telegram_sync, outreach=outreach,
    ))
    if mode == "preflight":
        status = "ok" if check["ready"] else "failed"
        detail = "canonical bundle present" if check["ready"] else "missing canonical files"
        report["steps"].append({"name": "preflight", "status": status, "detail": detail})
        report["ok"] = check["ready"]
        report["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return report
    if not check["ready"]:
        report["steps"].append({
            "name": "preflight",
            "status": "failed",
            "detail": "refusing to write; canonical bundle incomplete",
        })
        report["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return report

    jt = job_tracker_dir()
    env = _child_env()
    if notifications:
        env["ENABLE_NOTIFICATIONS"] = "1"
    copied = backup_state(jt)
    report["steps"].append({"name": "backup", "status": "ok", "detail": f"snapshotted {len(copied)} files"})

    def step_script(name, script: Path, args):
        code, detail = _run_py(script, args, env)
        report["steps"].append({
            "name": name,
            "status": "ok" if code == 0 else "failed",
            "detail": detail or f"exit {code}",
        })
        return code == 0

    if mode == "applied-sync":
        ok = step_script("process_inbox", SCRIPTS_DIR / "process_inbox.py", [])
        ok = ok and step_script("merge_referral_updates", jt / "merge_referral_updates.py", [])
        if ok:
            built, detail = _guarded_build(env, allow_needed=False, allow_new_jobs=False)
            report["steps"].append({"name": "build_site", "status": "ok" if built else "failed", "detail": detail})
            ok = built
    elif mode == "crawl":
        ok = step_script("sweep_crawler", SCRIPTS_DIR / "sweep_crawler.py", [])
        ok = ok and step_script("auto_referral_needed", jt / "auto_referral_needed.py", [])
        ok = ok and step_script("merge_referral_updates", jt / "merge_referral_updates.py", [])
        if telegram_sync:
            ok = ok and step_script("telegram_sync", SCRIPTS_DIR / "sync_applied_from_telegram.py", [])
        found = jt / "found_jobs_latest.json"
        gen_args = ["--jobs", str(found)]
        if not notifications:
            gen_args.append("--no-telegram")
        if ok and found.exists():
            ok = step_script("generate_report", SCRIPTS_DIR / "generate_report.py", gen_args)
        elif ok:
            report["steps"].append({
                "name": "generate_report",
                "status": "failed",
                "detail": "found_jobs_latest.json was not written",
            })
            ok = False
        ok = ok and step_script("auto_referral_needed_after", jt / "auto_referral_needed.py", [])
        ok = ok and step_script("merge_referral_updates_after", jt / "merge_referral_updates.py", [])
        if outreach:
            ok = ok and step_script("outreach", jt / "outreach_queue.py", [])
        if ok:
            built, detail = _guarded_build(env, allow_needed=True, allow_new_jobs=True)
            report["steps"].append({"name": "build_site", "status": "ok" if built else "failed", "detail": detail})
            ok = built
    else:
        report["steps"].append({"name": "mode", "status": "failed", "detail": f"unknown mode {mode}"})
        ok = False

    report["ok"] = bool(ok)
    report["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return report


def write_health(report: dict) -> Path:
    path = REPO_ROOT / "state" / "health.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    from updates_lib import atomic_write_json
    atomic_write_json(path, json.loads(redact(json.dumps(report))))
    return path


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=["preflight", "applied-sync", "crawl"])
    parser.add_argument("--publish", action="store_true", help="Write health and, with --git-push, commit on success")
    parser.add_argument("--git-push", action="store_true")
    parser.add_argument("--notifications", action="store_true")
    parser.add_argument("--telegram-sync", action="store_true")
    parser.add_argument("--outreach", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "preflight" and (args.publish or args.git_push):
        print(json.dumps({"ok": False, "detail": "preflight does not publish"}))
        return 2

    def once():
        return execute(
            args.mode,
            notifications=args.notifications,
            telegram_sync=args.telegram_sync,
            outreach=args.outreach,
        )

    if not args.git_push:
        report = once()
        text = redact(json.dumps(report, indent=2))
        print(text)
        if args.publish and report["ok"]:
            write_health(report)
        return 0 if report["ok"] else 2

    from git_publish import GitPublisher
    publisher = GitPublisher(REPO_ROOT, allow_reset=True)
    holder = {}

    def mutate():
        report = once()
        holder["report"] = report
        if not report["ok"]:
            raise RuntimeError("pipeline failed; not committing")
        write_health(report)

    try:
        published = publisher.sync_publish(
            PUBLISH_PATHS,
            f"Hosted {args.mode}",
            mutate,
        )
    except Exception as exc:
        publisher.reset_to_origin()
        report = holder.get("report") or {"ok": False, "mode": args.mode, "steps": []}
        report["ok"] = False
        report["publish"] = {"ok": False, "detail": redact(exc)}
        print(redact(json.dumps(report, indent=2)))
        return 2
    report = holder.get("report") or {"ok": False}
    report["publish"] = published
    print(redact(json.dumps(report, indent=2)))
    return 0 if report.get("ok") and published.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())

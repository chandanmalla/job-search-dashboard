"""Flag new best-matching jobs as referral status 'needed'.

Reads and writes only under JT_DIR. Prints a count. Per-job lines stay off
unless AUTO_REF_VERBOSE=1, so a public log does not list roles.
"""
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import job_tracker_dir

BASE = job_tracker_dir()
TRACKED = BASE / "tracked_jobs.json"
UPDATES = BASE / "referral_updates.json"
STATE = BASE / "auto_referral_state.json"
DIRECT_FILE = BASE / "direct_apply_companies.json"
ALLOW_FILE = BASE / "referral_other_allowlist.json"
IST = timezone(timedelta(hours=5, minutes=30))
ROLE = re.compile(
    r"(data scien|applied scien|lead scien|machine learning scien|ml scien|research scien|decision scien)",
    re.I,
)
BAD = re.compile(r"(^analyst|\banalyst-|principal|director|head of|intern|junior|\bjr\b|graduate|contract)", re.I)


def num(job_id):
    match = re.search(r"\d+", job_id or "")
    return int(match.group()) if match else -1


def write_atomic(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(obj, handle, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def main(argv):
    import job_filters as filters
    dry = "--dry-run" in argv
    since = int(argv[argv.index("--since-id") + 1]) if "--since-id" in argv else None
    data = json.loads(TRACKED.read_text(encoding="utf-8"))
    jobs = data.get("all_jobs", [])
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    watermark = since if since is not None else state.get("watermark")
    max_id = max((num(job.get("job_id")) for job in jobs), default=0)
    if watermark is None:
        if not dry:
            write_atomic(STATE, {"watermark": max_id})
        print(f"[auto_ref] initialised watermark count_only max_id={max_id}")
        return
    direct = set()
    if DIRECT_FILE.exists():
        direct = {item.strip().lower() for item in json.loads(DIRECT_FILE.read_text(encoding="utf-8"))}
    done = set(data.get("applied", [])) | set(data.get("skipped", []))
    updates = json.loads(UPDATES.read_text(encoding="utf-8") or "[]") if UPDATES.exists() else []
    have = {row.get("job_id") for row in updates}
    now = datetime.now(IST).strftime("%Y-%m-%dT%H:%M+05:30")
    added = 0
    for job in jobs:
        job_id = job.get("job_id")
        company = (job.get("company") or "").strip()
        title = job.get("job_title") or ""
        if num(job_id) <= watermark or job_id in have or job_id in done:
            continue
        if (job.get("status") or "").lower() in ("applied", "skipped"):
            continue
        if ((job.get("referral") or {}).get("status") or "none") != "none":
            continue
        if company.lower() in direct or not ROLE.search(title) or BAD.search(title) or job.get("stretch"):
            continue
        if not str(job.get("experience_fit", "")).lower().startswith("strong"):
            continue
        low, high = job.get("_exp_min"), job.get("_exp_max")
        if (low is not None and low > 7) or (high is not None and high < 3):
            continue
        if not filters.company_product(company):
            continue
        top, _reason = filters.visibility(dict(job))
        if not top:
            ok, _reason = filters.visibility(dict(job), require_top=False)
            if not ok:
                continue
        updates.append({
            "job_id": job_id,
            "status": "needed",
            "contacts": [],
            "updated_at": now,
            "source": "auto_best_match",
        })
        have.add(job_id)
        added += 1
        if os.environ.get("AUTO_REF_VERBOSE") == "1":
            print("[auto_ref] flagged one job")
    if not dry:
        if added:
            write_atomic(UPDATES, updates)
        write_atomic(STATE, {"watermark": max(max_id, watermark)})
    print(f"[auto_ref] {'dry ' if dry else ''}flagged={added}")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception:
        print("[auto_ref] ERROR (non-fatal)")
    sys.exit(0)

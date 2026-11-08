"""Merge referral, applied, and skipped update logs into tracked_jobs.json.

The data directory is JT_DIR (the private canonical store). This file is code only.
A run that replays the logs but leaves the canonical JSON logically unchanged
does not rewrite the file. Unknown job ids are counted, not printed.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import job_tracker_dir

BASE = job_tracker_dir()
TRACKED = Path(os.environ.get("JT_TRACKED", BASE / "tracked_jobs.json"))
UPDATES = Path(os.environ.get("JT_REF_UPDATES", BASE / "referral_updates.json"))
APPLIED_UPDATES = Path(os.environ.get("JT_APPLIED_UPDATES", BASE / "applied_updates.json"))
SKIPPED_UPDATES = Path(os.environ.get("JT_SKIPPED_UPDATES", BASE / "skipped_updates.json"))
IST = timezone(timedelta(hours=5, minutes=30))
TS_FIELDS = ("first_message_at", "reminder_at")


def ts(value):
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%dT%H:%M%z"):
        try:
            parsed = datetime.fromisoformat(text) if fmt is None else datetime.strptime(text, fmt)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=IST)
        except Exception:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def merge_contacts(old, new, newer):
    by_key = {}
    order = []
    for contact in old or []:
        key = contact.get("profile_url") or contact.get("name")
        by_key[key] = dict(contact)
        order.append(key)
    for contact in new or []:
        key = contact.get("profile_url") or contact.get("name")
        if key not in by_key:
            by_key[key] = dict(contact)
            order.append(key)
            continue
        current = by_key[key]
        for field, value in contact.items():
            if value is None or value == "":
                continue
            if field in TS_FIELDS:
                if not current.get(field):
                    current[field] = value
                continue
            if field == "replied":
                current[field] = bool(current.get(field)) or bool(value)
                continue
            if newer or not current.get(field):
                current[field] = value
    return [by_key[key] for key in order]


def _canon(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def main():
    for path in (UPDATES, APPLIED_UPDATES):
        if not path.exists():
            _write(path, [])
            print(f"[merge] created empty {path.name}")
    try:
        updates = json.loads(UPDATES.read_text(encoding="utf-8") or "[]")
        applied_updates = json.loads(APPLIED_UPDATES.read_text(encoding="utf-8") or "[]")
    except Exception:
        print("[merge] ERROR reading updates file")
        return 1
    data = json.loads(TRACKED.read_text(encoding="utf-8"))
    before = _canon(data)
    jobs = {job.get("job_id"): job for job in data.get("all_jobs", [])}
    missing = []
    direct_file = BASE / "direct_apply_companies.json"
    direct = set()
    if direct_file.exists():
        direct = {item.strip().lower() for item in json.loads(direct_file.read_text(encoding="utf-8"))}
    applied_ids = set(data.get("applied", [])) | set(data.get("skipped", []))
    now = datetime.now(IST).strftime("%Y-%m-%dT%H:%M+05:30")
    for job in jobs.values():
        if (job.get("company") or "").strip().lower() not in direct or not job.get("dashboard_visible"):
            continue
        if job.get("status") in ("Applied", "Skipped") or job.get("job_id") in applied_ids:
            continue
        referral = job.get("referral") or {"status": "none", "contacts": [], "updated_at": None}
        if (referral.get("status") or "none") == "none":
            referral["status"] = "apply_direct"
            referral["updated_at"] = now
            job["referral"] = referral
    for update in sorted(updates, key=lambda row: ts(row.get("updated_at"))):
        job = jobs.get(update.get("job_id"))
        if job is None:
            missing.append(update.get("job_id"))
            continue
        referral = job.get("referral") or {"status": "none", "contacts": [], "updated_at": None}
        newer = ts(update.get("updated_at")) > ts(referral.get("updated_at"))
        if newer and update.get("status"):
            referral["status"] = update["status"]
            referral["updated_at"] = update.get("updated_at")
        referral["contacts"] = merge_contacts(referral.get("contacts"), update.get("contacts"), newer)
        job["referral"] = referral
    applied_list = data.setdefault("applied", [])
    skipped_list = data.setdefault("skipped", [])
    applied_set = set(applied_list)
    skipped_set = set(skipped_list)
    n_applied = 0
    for update in applied_updates:
        job_id = update.get("job_id")
        if not job_id:
            continue
        job = jobs.get(job_id)
        if job is None:
            missing.append(job_id)
        dirty = False
        if job_id not in applied_set:
            applied_set.add(job_id)
            dirty = True
        if job_id in skipped_set:
            skipped_set.discard(job_id)
            dirty = True
        if job is not None:
            if job.get("status") != "Applied":
                job["status"] = "Applied"
                dirty = True
            if update.get("applied_at") and not job.get("applied_at"):
                job["applied_at"] = update["applied_at"]
                dirty = True
        if dirty:
            n_applied += 1
    if n_applied:
        data["applied"] = sorted(applied_set)
        data["skipped"] = sorted(skipped_set)
    try:
        skipped_updates = json.loads(SKIPPED_UPDATES.read_text(encoding="utf-8") or "[]") if SKIPPED_UPDATES.exists() else []
    except Exception:
        print("[merge] ERROR reading skipped_updates")
        return 1
    skipped_ids = set(data.get("skipped", []))
    applied_now = set(data.get("applied", []))
    n_skipped = 0
    for update in skipped_updates:
        job_id = update.get("job_id")
        job = jobs.get(job_id)
        if not job_id or job_id in applied_now:
            continue
        if update.get("action") == "unskip":
            if job is None:
                missing.append(job_id)
                continue
            if job_id in skipped_ids or job.get("status") == "Skipped":
                skipped_ids.discard(job_id)
                job["status"] = None
                job.pop("skipped_at", None)
                referral = job.get("referral") or {"contacts": []}
                if referral.get("status") in (None, "skipped"):
                    referral["status"] = "none"
                    referral["updated_at"] = update.get("unskipped_at")
                    job["referral"] = referral
                try:
                    import job_filters as filters
                    job["dashboard_visible"], job["hide_reason"] = filters.visibility(dict(job))
                except Exception:
                    print("[merge] unskip visibility error")
                n_skipped += 1
            continue
        if job is None:
            missing.append(job_id)
            continue
        dirty = False
        if job_id not in skipped_ids:
            skipped_ids.add(job_id)
            dirty = True
        if job.get("status") != "Skipped":
            job["status"] = "Skipped"
            dirty = True
        if update.get("skipped_at") and not job.get("skipped_at"):
            job["skipped_at"] = update["skipped_at"]
            dirty = True
        if job.get("dashboard_visible"):
            job["dashboard_visible"] = False
            dirty = True
        referral = job.get("referral") or {"contacts": []}
        if referral.get("status") != "skipped":
            referral["status"] = "skipped"
            referral["updated_at"] = update.get("skipped_at")
            job["referral"] = referral
            dirty = True
        if dirty:
            n_skipped += 1
    if n_skipped:
        data["skipped"] = sorted(skipped_ids)
    changed = 0 if _canon(data) == before else 1
    if changed:
        _write(TRACKED, data)
    unknown = len({job_id for job_id in missing if job_id})
    print(
        f"[merge] {len(updates)} referral + {len(applied_updates)} applied records, "
        f"rewritten={changed} (applied_touches={n_applied}, skipped_touches={n_skipped}, "
        f"unknown_job_id_count={unknown})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

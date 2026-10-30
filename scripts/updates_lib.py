"""Shared helper: append applied/skipped/referred marks to job-tracker/*_updates.json (deduped).
Never writes tracked_jobs.json; merge_referral_updates.py applies these files."""
import json, os, tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

JT = Path(os.environ.get("JT_DIR", r"C:\Users\chand\Downloads\Job Search\job-tracker"))
IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    return datetime.now(IST).strftime("%Y-%m-%dT%H:%M+05:30")

def _load(p):
    try:
        return json.loads(p.read_text(encoding="utf-8") or "[]") if p.exists() else []
    except Exception:
        raise RuntimeError(f"cannot parse {p.name}; refusing to overwrite")

def _save(p, data):
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)

def append_updates(applied=(), skipped=(), referred=()):
    """Each arg: iterable of (job_id, iso_ts or None). Returns counts of newly added records."""
    out = {"applied": 0, "skipped": 0, "referred": 0}
    spec = [("applied", "applied_updates.json", "applied_at", applied),
            ("skipped", "skipped_updates.json", "skipped_at", skipped)]
    for name, fn, tsk, items in spec:
        items = list(items)
        if not items: continue
        p = JT / fn; data = _load(p); have = {r.get("job_id") for r in data}
        for jid, t in items:
            jid = (jid or "").strip().upper()
            if not jid or jid in have: continue
            data.append({"job_id": jid, tsk: t or now_ist()}); have.add(jid); out[name] += 1
        if out[name]: _save(p, data)
    items = list(referred)
    if items:
        p = JT / "referral_updates.json"; data = _load(p)
        have = {r.get("job_id") for r in data if r.get("status") == "referred"}
        for jid, t in items:
            jid = (jid or "").strip().upper()
            if not jid or jid in have: continue
            data.append({"job_id": jid, "status": "referred", "contacts": [], "updated_at": t or now_ist()})
            have.add(jid); out["referred"] += 1
        if out["referred"]: _save(p, data)
    return out

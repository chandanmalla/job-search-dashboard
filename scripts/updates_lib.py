"""Append applied/skipped/referred marks to job-tracker/*_updates.json (deduped).

Never writes tracked_jobs.json. merge_referral_updates.py applies these files.
Paths come from JT_DIR or the portable default. Writes are atomic and locked.
"""
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from file_lock import state_lock
from paths import job_tracker_dir

IST = timezone(timedelta(hours=5, minutes=30))


def jt_dir() -> Path:
    return job_tracker_dir()


class _JT:
    """U.JT / 'name.json' reads JT_DIR on each use."""

    def __truediv__(self, other):
        return jt_dir() / other

    def __str__(self):
        return str(jt_dir())


JT = _JT()


def now_ist():
    return datetime.now(IST).strftime("%Y-%m-%dT%H:%M+05:30")


def atomic_write_json(path: Path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load(path: Path):
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8") or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"cannot parse {path.name}; refusing to overwrite") from exc


def _save(path: Path, data):
    atomic_write_json(path, data)


def append_updates(applied=(), skipped=(), referred=()):
    """Each arg: iterable of (job_id, iso_ts or None). Returns counts of newly added records."""
    with state_lock(jt_dir()):
        return _append_unlocked(applied, skipped, referred)


def _append_unlocked(applied=(), skipped=(), referred=()):
    out = {"applied": 0, "skipped": 0, "referred": 0}
    spec = [
        ("applied", "applied_updates.json", "applied_at", applied),
        ("skipped", "skipped_updates.json", "skipped_at", skipped),
    ]
    root = jt_dir()
    for name, filename, stamp_key, items in spec:
        items = list(items)
        if not items:
            continue
        path = root / filename
        data = _load(path)
        if not isinstance(data, list):
            raise RuntimeError(f"{filename} is not a list; refusing to overwrite")
        have = {str(record.get("job_id") or "").upper() for record in data}
        for job_id, stamp in items:
            job_id = (job_id or "").strip().upper()
            if not job_id or job_id in have:
                continue
            data.append({"job_id": job_id, stamp_key: stamp or now_ist()})
            have.add(job_id)
            out[name] += 1
        if out[name]:
            _save(path, data)
    items = list(referred)
    if items:
        path = root / "referral_updates.json"
        data = _load(path)
        if not isinstance(data, list):
            raise RuntimeError("referral_updates.json is not a list; refusing to overwrite")
        have = {str(record.get("job_id") or "").upper() for record in data if record.get("status") == "referred"}
        for job_id, stamp in items:
            job_id = (job_id or "").strip().upper()
            if not job_id or job_id in have:
                continue
            data.append({
                "job_id": job_id,
                "status": "referred",
                "contacts": [],
                "updated_at": stamp or now_ist(),
            })
            have.add(job_id)
            out["referred"] += 1
        if out["referred"]:
            _save(path, data)
    return out

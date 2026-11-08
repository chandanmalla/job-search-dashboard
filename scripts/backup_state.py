"""Timestamped copies of canonical JSON before a publish. Git history is the durable log."""
import shutil
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT_NAMES = (
    "tracked_jobs.json",
    "applied_updates.json",
    "skipped_updates.json",
    "referral_updates.json",
    "cron_state.json",
)
KEEP = 5


def backup_state(jt: Path, keep: int = KEEP, stamp: str | None = None) -> list:
    jt = Path(jt)
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = jt / "backups" / stamp
    copied = []
    for name in SNAPSHOT_NAMES:
        src = jt / name
        if not src.is_file():
            continue
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest / name)
        copied.append(name)
    root = jt / "backups"
    if root.is_dir():
        dirs = sorted(p for p in root.iterdir() if p.is_dir())
        for old in dirs[:-keep] if keep > 0 else dirs:
            shutil.rmtree(old)
    return copied

"""Move website marks from data/applied_inbox.json into job-tracker/*_updates.json.

Entry format written by the dashboard: {"job_id": "J123", "action": "applied|skipped|referred", "ts": ISO}.
Processed fingerprints are removed. Unrecognized entries stay in the inbox.
A retry or a second writer does not duplicate update records. The inbox is left
unchanged if the updates files cannot be parsed.

Usage: process_inbox.py [--dry-run]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import updates_lib as U
from file_lock import state_lock
from paths import inbox_path
from redact import redact

ACTIONS = ("applied", "skipped", "referred")


def fingerprint(entry: dict) -> tuple:
    return (
        str(entry.get("job_id") or "").strip().upper(),
        str(entry.get("action") or "").strip().lower(),
        str(entry.get("ts") or ""),
    )


def _read_inbox(path: Path):
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"cannot parse inbox; leaving it untouched: {exc}") from exc
    if not isinstance(data, list):
        raise RuntimeError("inbox is not a list; leaving it untouched")
    return data


def main():
    dry = "--dry-run" in sys.argv
    inbox = inbox_path()
    if not inbox.exists():
        if dry:
            print("[inbox] No inbox file.")
            return 0
        inbox.parent.mkdir(parents=True, exist_ok=True)
        U.atomic_write_json(inbox, [])
        print("[inbox] created empty applied_inbox.json")
        return 0
    try:
        with state_lock(U.jt_dir()):
            entries = _read_inbox(inbox)
            if not entries:
                print("[inbox] No website marks pending.")
                return 0
            buckets = {name: [] for name in ACTIONS}
            processed = []
            ignored = []
            for entry in entries:
                if not isinstance(entry, dict):
                    ignored.append(entry)
                    continue
                action = (entry.get("action") or "").lower()
                job_id = (entry.get("job_id") or "").strip()
                if action in buckets and job_id:
                    buckets[action].append((job_id, entry.get("ts")))
                    processed.append(entry)
                else:
                    ignored.append(entry)
            if dry:
                summary = ", ".join(f"{name}={len(buckets[name])}" for name in ACTIONS)
                print(f"[inbox] DRY RUN: would add {summary}, ignored={len(ignored)}")
                return 0
            try:
                added = U._append_unlocked(**buckets)
            except Exception as exc:
                print(f"[inbox] ERROR updates not written; inbox unchanged: {redact(exc)}")
                return 1
            done = {fingerprint(entry) for entry in processed}
            current = _read_inbox(inbox)
            kept = []
            for entry in current:
                if isinstance(entry, dict) and fingerprint(entry) in done:
                    continue
                kept.append(entry)
            U.atomic_write_json(inbox, kept)
    except RuntimeError as exc:
        print(f"[inbox] ERROR {redact(exc)}")
        return 1
    ids = [entry.get("job_id") for entry in processed]
    print(
        f"[inbox] {len(entries)} website marks -> new records {added}, "
        f"ignored={len(ignored)} kept; inbox_remaining={len(kept)}; ids={ids}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Move website marks from data/applied_inbox.json into job-tracker/*_updates.json, then clear the inbox.
Entry format written by the dashboard: {"job_id": "J123", "action": "applied|skipped|referred", "ts": ISO}.
Usage: process_inbox.py [--dry-run]"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import updates_lib as U

INBOX = Path(__file__).parent.parent / "data" / "applied_inbox.json"

def main():
    dry = "--dry-run" in sys.argv
    if not INBOX.exists():
        INBOX.write_text("[]\n", encoding="utf-8"); print("[inbox] created empty applied_inbox.json"); return 0
    try:
        entries = json.loads(INBOX.read_text(encoding="utf-8") or "[]")
    except Exception as e:
        print(f"[inbox] ERROR parsing inbox, leaving it untouched: {e}"); return 1
    if not entries:
        print("[inbox] No website marks pending."); return 0
    buckets = {"applied": [], "skipped": [], "referred": []}; ignored = 0
    for e in entries:
        a = (e.get("action") or "").lower()
        if a in buckets and e.get("job_id"):
            buckets[a].append((e["job_id"], e.get("ts")))
        else:
            ignored += 1
    if dry:
        print(f"[inbox] DRY RUN: would add {', '.join(f'{k}={len(v)}' for k,v in buckets.items())}, ignored={ignored}"); return 0
    res = U.append_updates(**buckets)
    INBOX.write_text("[]\n", encoding="utf-8")
    print(f"[inbox] {len(entries)} website marks -> new records {res}, ignored={ignored}; inbox cleared")
    return 0

if __name__ == "__main__":
    sys.exit(main())

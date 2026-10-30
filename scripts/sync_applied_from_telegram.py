"""
Sync Applied Jobs From Telegram
===============================
Called at the beginning of each 2-hour cron run (or on-demand).
Pulls all pending /applied and /skip messages sent to the Telegram bot,
appends them to job-tracker/*_updates.json (merged by merge_referral_updates.py),
and acknowledges the messages. Never writes tracked_jobs.json; the Telegram offset lives in tg_offset.json.

Supports single or multiple IDs in one command:
    /applied J001
    /applied J001 J004 J046
    /skip J002 J010
"""

import json
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_DIR = Path(__file__).parent.parent
CONFIG_PATH = Path(r"C:\Users\chand\Downloads\Job Search\job-tracker\config.json")

def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)

def load_db(path):
    p = Path(path)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"seen_keys": [], "all_jobs": [], "applied": [], "skipped": [], "last_tg_offset": 0}

def save_db(path, db):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def tg_send(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": "true"
    }
    data = urllib.parse.urlencode(payload).encode()
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"[sync_tg] send error: {e}")
        return {"ok": False}

import sys as _sys
_sys.path.insert(0, r"C:\Users\chand\Downloads\Job Search\job-tracker")
import job_filters as JF
_sys.path.insert(0, str(Path(__file__).parent))
import updates_lib as U
OFFSET_PATH = Path(r"C:\Users\chand\Downloads\Job Search\job-tracker\tg_offset.json")

def load_offset(db):
    try:
        return int(json.loads(OFFSET_PATH.read_text(encoding='utf-8')).get('last_tg_offset', 0))
    except Exception:
        return int(db.get('last_tg_offset', 0) or 0)

def save_offset(off):
    OFFSET_PATH.write_text(json.dumps({'last_tg_offset': off}), encoding='utf-8')

def sync_from_telegram():
    cfg = load_config()
    token = cfg["telegram"]["bot_token"]
    raw_cids = cfg["telegram"].get("chat_ids") or [cfg["telegram"].get("chat_id")]
    allowed_chat_ids = set(str(c) for c in raw_cids if c)
    db_path = cfg["tracked_jobs_db"]

    db = load_db(db_path)
    offset = load_offset(db)

    url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=2"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"[sync_tg] Failed to fetch updates: {e}")
        return []

    updates = data.get("result", [])
    if not updates:
        print("[sync_tg] No pending Telegram messages.")
        return []

    applied_set = set(db.setdefault("applied", []))
    skipped_set = set(db.setdefault("skipped", []))
    jobs_map = {j.get("job_id", "").upper(): j for j in db.get("all_jobs", [])}

    newly_actioned = []
    upd_applied, upd_skipped, upd_referred, upd_direct = [], [], [], []

    for upd in updates:
        offset = upd["update_id"] + 1
        msg = upd.get("message", {})
        text = msg.get("text", "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))

        if chat_id not in allowed_chat_ids or not text.startswith("/"):
            continue

        parts = text.replace(",", " ").split()
        cmd = parts[0].lower().lstrip("/").split("@")[0]
        ids = [p.upper() for p in parts[1:] if p.upper().startswith("J") or p.isdigit()]

        if not ids:
            continue

        if cmd == "applied":
            for jid in ids:
                upd_applied.append((jid, None))
                newly_actioned.append((jid, "Applied"))
            tg_send(token, chat_id, f"âœ… Marked as *Applied*: `{', '.join(ids)}`\n_Excluded from future sweeps and updated on dashboard._")

        elif cmd == "skip":
            for jid in ids:
                upd_skipped.append((jid, None))
                newly_actioned.append((jid, "Skipped"))
            tg_send(token, chat_id, f"ðŸš« Marked as *Skipped*: `{', '.join(ids)}`\n_Hidden from future sweeps._")

        elif cmd in ("referred", "direct"):
            new_status = "referred" if cmd == "referred" else "apply_direct"
            for jid in ids:
                if new_status == "referred":
                    upd_referred.append((jid, None))
                else:
                    upd_direct.append(jid)
                newly_actioned.append((jid, new_status))
            tg_send(token, chat_id, f"Referral status set to *{new_status}*: `{', '.join(ids)}`")

    res = U.append_updates(applied=upd_applied, skipped=upd_skipped, referred=upd_referred)
    if upd_direct:
        import json as _j
        p = U.JT / "referral_updates.json"; data = _j.loads(p.read_text(encoding="utf-8") or "[]") if p.exists() else []
        for jid in upd_direct:
            data.append({"job_id": jid, "status": "apply_direct", "contacts": [], "updated_at": U.now_ist()})
        U._save(p, data)
    save_offset(offset)
    print(f"[sync_tg] queued update records: {res}, apply_direct={len(upd_direct)}")

    print(f"[sync_tg] Processed {len(newly_actioned)} actions from Telegram. New offset: {offset}")
    return newly_actioned

if __name__ == "__main__":
    actions = sync_from_telegram()
    print("Sync complete. Actions:", actions)

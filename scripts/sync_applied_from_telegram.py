"""
Sync Applied Jobs From Telegram
===============================
Called at the beginning of each 3-hour cron run (or on-demand).
Pulls all pending /applied and /skip messages sent to the Telegram bot,
updates tracked_jobs.json, and acknowledges the messages.

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

def sync_from_telegram():
    cfg = load_config()
    token = cfg["telegram"]["bot_token"]
    raw_cids = cfg["telegram"].get("chat_ids") or [cfg["telegram"].get("chat_id")]
    allowed_chat_ids = set(str(c) for c in raw_cids if c)
    db_path = cfg["tracked_jobs_db"]

    db = load_db(db_path)
    offset = db.get("last_tg_offset", 0)

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
                applied_set.add(jid)
                skipped_set.discard(jid)
                if jid in jobs_map:
                    jobs_map[jid]["status"] = "Applied"
                newly_actioned.append((jid, "Applied"))
            tg_send(token, chat_id, f"✅ Marked as *Applied*: `{', '.join(ids)}`\n_Excluded from future sweeps and updated on dashboard._")

        elif cmd == "skip":
            for jid in ids:
                skipped_set.add(jid)
                applied_set.discard(jid)
                if jid in jobs_map:
                    jobs_map[jid]["status"] = "Skipped"
                newly_actioned.append((jid, "Skipped"))
            tg_send(token, chat_id, f"🚫 Marked as *Skipped*: `{', '.join(ids)}`\n_Hidden from future sweeps._")

    db["applied"] = sorted(list(applied_set))
    db["skipped"] = sorted(list(skipped_set))
    db["last_tg_offset"] = offset
    save_db(db_path, db)

    print(f"[sync_tg] Processed {len(newly_actioned)} actions from Telegram. New offset: {offset}")
    return newly_actioned

if __name__ == "__main__":
    actions = sync_from_telegram()
    print("Sync complete. Actions:", actions)

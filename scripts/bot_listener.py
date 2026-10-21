"""
Telegram Bot Listener for Job Tracker
=======================================
Runs continuously, polling for Telegram commands:

  /applied J001      — mark job J001 as applied (never show again)
  /skip J001         — mark job J001 as not interested (never show again)
  /status            — show counts (tracked / applied / skipped)
  /list              — list all tracked job IDs with titles
  /help              — show available commands

Usage:
    python bot_listener.py
"""

import json
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_DIR  = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
POLL_INTERVAL = 3   # seconds between Telegram getUpdates calls

# ---------------------------------------------------------------------------
# Config & DB helpers
# ---------------------------------------------------------------------------

def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)

def load_db(path: str) -> dict:
    p = Path(path)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"seen_keys": [], "all_jobs": [], "applied": [], "skipped": []}

def save_db(path: str, db: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------

def tg_request(token: str, method: str, payload: dict) -> dict:
    url  = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(payload).encode()
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"[tg] {method} error: {e}", flush=True)
        return {"ok": False}

def get_updates(token: str, offset: int) -> list:
    result = tg_request(token, "getUpdates", {
        "offset": offset,
        "timeout": 2,
        "allowed_updates": "message"
    })
    if result.get("ok"):
        return result.get("result", [])
    return []

def send_message(token: str, chat_id: str, text: str):
    tg_request(token, "sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": "true"
    })

# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def find_job(db: dict, job_id: str) -> dict | None:
    jid = job_id.upper().strip()
    for j in db.get("all_jobs", []):
        if j.get("job_id", "").upper() == jid:
            return j
    return None

def handle_applied(token, chat_id, db, db_path, args):
    if not args:
        send_message(token, chat_id,
            "⚠️ Usage: `/applied J001`\nProvide the Job ID from the Telegram card.")
        return
    jid = args[0].upper()
    job = find_job(db, jid)
    if not job:
        send_message(token, chat_id,
            f"❌ Job ID `{jid}` not found.\nUse `/list` to see all tracked job IDs.")
        return
    applied = db.setdefault("applied", [])
    if jid in applied:
        send_message(token, chat_id,
            f"ℹ️ `{jid}` — *{job.get('job_title','')}* at *{job.get('company','')}* "
            f"was already marked as applied.")
        return
    applied.append(jid)
    job["status"] = "Applied"
    save_db(db_path, db)
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    send_message(token, chat_id,
        f"✅ Marked as *Applied* at {ts}\n\n"
        f"*{jid}* — {job.get('job_title','')} @ {job.get('company','')}\n"
        f"📍 {job.get('location','')}\n\n"
        f"_This job will not be shown in future alerts._")

def handle_skip(token, chat_id, db, db_path, args):
    if not args:
        send_message(token, chat_id,
            "⚠️ Usage: `/skip J001`\nProvide the Job ID from the Telegram card.")
        return
    jid = args[0].upper()
    job = find_job(db, jid)
    if not job:
        send_message(token, chat_id,
            f"❌ Job ID `{jid}` not found.\nUse `/list` to see all tracked job IDs.")
        return
    skipped = db.setdefault("skipped", [])
    if jid in skipped:
        send_message(token, chat_id,
            f"ℹ️ `{jid}` was already marked as skipped.")
        return
    skipped.append(jid)
    job["status"] = "Skipped"
    save_db(db_path, db)
    send_message(token, chat_id,
        f"🚫 Marked as *Not Interested*\n\n"
        f"*{jid}* — {job.get('job_title','')} @ {job.get('company','')}\n\n"
        f"_This job will not appear in future alerts._")

def handle_status(token, chat_id, db):
    all_jobs  = db.get("all_jobs", [])
    applied   = db.get("applied", [])
    skipped   = db.get("skipped", [])
    active    = [j for j in all_jobs
                 if j.get("job_id","") not in applied
                 and j.get("job_id","") not in skipped]
    msg = (
        f"📊 *Job Tracker Status*\n\n"
        f"📋 Total tracked: *{len(all_jobs)}*\n"
        f"✅ Applied: *{len(applied)}*\n"
        f"🚫 Skipped: *{len(skipped)}*\n"
        f"🔍 Still active: *{len(active)}*\n\n"
        f"Use `/list` to see active jobs with IDs.\n"
        f"Use `/applied J001` to mark a job as applied.\n"
        f"Use `/skip J001` to hide a job."
    )
    send_message(token, chat_id, msg)

def handle_list(token, chat_id, db):
    all_jobs = db.get("all_jobs", [])
    applied  = set(db.get("applied", []))
    skipped  = set(db.get("skipped", []))
    lines    = ["📋 *All Tracked Jobs*\n"]
    for j in all_jobs:
        jid    = j.get("job_id", "?")
        status = ""
        if jid in applied:
            status = " ✅ Applied"
        elif jid in skipped:
            status = " 🚫 Skipped"
        lines.append(f"`{jid}` {j.get('company','')} — {j.get('job_title','')[:40]}{status}")

    # Telegram max 4096 chars — split if needed
    chunks, current = [], ""
    for line in lines:
        if len(current) + len(line) + 1 > 3800:
            chunks.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current:
        chunks.append(current)
    for chunk in chunks:
        send_message(token, chat_id, chunk)

def handle_help(token, chat_id):
    msg = (
        "🤖 *Job Tracker Bot — Commands*\n\n"
        "`/applied J001` — Mark job as Applied (won't appear again)\n"
        "`/skip J001` — Mark as Not Interested (won't appear again)\n"
        "`/status` — Show counts (tracked / applied / skipped)\n"
        "`/list` — List all tracked jobs with IDs\n"
        "`/help` — Show this message\n\n"
        "_Job IDs are shown on every job card sent to this chat._"
    )
    send_message(token, chat_id, msg)

# ---------------------------------------------------------------------------
# Main polling loop
# ---------------------------------------------------------------------------

def main():
    cfg     = load_config()
    token   = cfg["telegram"]["bot_token"]
    raw_cids = cfg["telegram"].get("chat_ids") or [cfg["telegram"].get("chat_id")]
    allowed_chat_ids = set(str(c) for c in raw_cids if c)
    db_path = cfg["tracked_jobs_db"]

    print(f"[bot] Starting listener for chats {allowed_chat_ids}. Polling every {POLL_INTERVAL}s …", flush=True)
    for cid in allowed_chat_ids:
        send_message(token, cid,
            "🤖 *Job Tracker Bot is online!*\n\n"
            "Send `/help` to see all commands.\n"
            "Send `/list` to see all tracked job IDs.\n"
            "Send `/applied J001` to mark a job as applied.")

    offset = 0
    while True:
        try:
            updates = get_updates(token, offset)
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                text = msg.get("text", "").strip()
                if not text.startswith("/"):
                    continue

                # Only respond to authorized chats
                incoming_chat_id = str(msg.get("chat", {}).get("id", ""))
                if incoming_chat_id not in allowed_chat_ids:
                    continue

                parts   = text.split()
                command = parts[0].lower().lstrip("/").split("@")[0]
                args    = parts[1:]

                db = load_db(db_path)  # reload fresh each time

                print(f"[bot] Command from {incoming_chat_id}: {command} {args}", flush=True)

                if command == "applied":
                    handle_applied(token, incoming_chat_id, db, db_path, args)
                elif command == "skip":
                    handle_skip(token, incoming_chat_id, db, db_path, args)
                elif command == "status":
                    handle_status(token, incoming_chat_id, db)
                elif command == "list":
                    handle_list(token, incoming_chat_id, db)
                elif command in ("help", "start"):
                    handle_help(token, incoming_chat_id)
                else:
                    send_message(token, incoming_chat_id,
                        f"❓ Unknown command `/{command}`.\nSend `/help` for available commands.")

        except KeyboardInterrupt:
            print("[bot] Stopped.", flush=True)
            break
        except Exception as e:
            print(f"[bot] Error: {e}", flush=True)

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()

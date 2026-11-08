"""Parse dashboard marks and append them to data/applied_inbox.json.

The GitHub-login path accepts issues only from an allow-listed account.
Token-shaped text is rejected and never written or printed.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from file_lock import state_lock
from paths import inbox_path, job_tracker_dir
from redact import redact
from updates_lib import atomic_write_json

MARKER = "dashboard-mark"
ACTIONS = ("applied", "skipped", "referred")
TOKEN_HINTS = ("ghp_", "github_pat_", "gho_", "xoxb-", "xoxp-", "xoxa-", "bot_token", "-----begin ")


def author_allowed(actor: str, authors_csv: str | None) -> bool:
    raw = authors_csv if authors_csv else "chandanmalla"
    allowed = {part.strip().lower() for part in raw.split(",") if part.strip()}
    if not allowed:
        allowed = {"chandanmalla"}
    return (actor or "").strip().lower() in allowed


def parse_mark_text(text: str) -> list:
    """Return [{job_id, action}] or raise ValueError if the text looks like a secret."""
    lowered = (text or "").lower()
    for hint in TOKEN_HINTS:
        if hint in lowered:
            raise ValueError("token-like content")
    marks = []
    seen = set()
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--") or stripped.startswith("#"):
            continue
        parts = stripped.replace(",", " ").split()
        if len(parts) < 2:
            continue
        action = parts[0].lower().lstrip("/")
        if action not in ACTIONS:
            continue
        for token in parts[1:]:
            job_id = token.strip().upper()
            if not job_id.startswith("J") or not job_id[1:].isdigit():
                continue
            key = (action, job_id)
            if key in seen:
                continue
            seen.add(key)
            marks.append({"job_id": job_id, "action": action})
            if len(marks) >= 100:
                return marks
    return marks


def append_marks(marks, *, ts: str) -> int:
    """Union marks into the inbox by (job_id, action, ts). Returns how many were new."""
    inbox = inbox_path()
    inbox.parent.mkdir(parents=True, exist_ok=True)
    with state_lock(job_tracker_dir()):
        if inbox.exists():
            try:
                current = json.loads(inbox.read_text(encoding="utf-8") or "[]")
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"inbox is not valid JSON; refusing to overwrite ({exc})") from exc
        else:
            current = []
        if not isinstance(current, list):
            raise RuntimeError("inbox is not a list; refusing to overwrite")
        have = set()
        for entry in current:
            if isinstance(entry, dict):
                have.add((str(entry.get("job_id") or "").upper(), str(entry.get("action") or "").lower(), str(entry.get("ts") or "")))
        added = 0
        for mark in marks:
            entry = {"job_id": mark["job_id"], "action": mark["action"], "ts": ts}
            key = (entry["job_id"], entry["action"], entry["ts"])
            if key in have:
                continue
            current.append(entry)
            have.add(key)
            added += 1
        atomic_write_json(inbox, current)
        return added


def handle_issue(*, actor: str, authors: str | None, title: str, body: str, enabled: bool, ts: str) -> dict:
    blob = f"{title}\n{body}"
    if MARKER not in blob and not (title or "").startswith("Dashboard marks"):
        return {"status": "ignored", "ids": [], "detail": "not a dashboard mark"}
    try:
        marks = parse_mark_text(blob)
    except ValueError:
        return {"status": "rejected", "ids": [], "detail": "token-like content refused"}
    if not author_allowed(actor, authors):
        return {"status": "rejected", "ids": [m["job_id"] for m in marks], "detail": "author not allow-listed"}
    if not marks:
        return {"status": "empty", "ids": [], "detail": "no marks parsed"}
    if not enabled:
        return {
            "status": "disabled",
            "ids": [f"{m['action']} {m['job_id']}" for m in marks],
            "detail": "HOSTED_MARK_ISSUES is not true; issue left as the record",
        }
    append_marks(marks, ts=ts)
    return {"status": "ok", "ids": [f"{m['action']} {m['job_id']}" for m in marks], "detail": "appended"}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["accept-issue"])
    parser.add_argument("--git-push", action="store_true")
    args = parser.parse_args(argv)
    actor = os.environ.get("MARK_ACTOR", "")
    authors = os.environ.get("MARK_AUTHORS")
    title = os.environ.get("ISSUE_TITLE", "")
    body = os.environ.get("ISSUE_BODY", "")
    enabled = os.environ.get("HOSTED_MARK_ISSUES") == "true"
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def apply():
        return handle_issue(actor=actor, authors=authors, title=title, body=body, enabled=enabled, ts=ts)

    result = apply()
    pushed = False
    if args.git_push and result["status"] == "ok":
        from git_publish import GitPublisher
        from paths import REPO_ROOT
        publisher = GitPublisher(REPO_ROOT, allow_reset=True)

        def mutate():
            handle_issue(actor=actor, authors=authors, title=title, body=body, enabled=True, ts=ts)

        published = publisher.sync_publish(
            ["data/applied_inbox.json"],
            "Dashboard marks from GitHub login",
            mutate,
        )
        result["detail"] = published["detail"]
        pushed = published["ok"] and published["pushed"]
        if not published["ok"]:
            result["status"] = "push_failed"
    out = {
        "status": result["status"],
        "ids": result["ids"],
        "detail": redact(result["detail"]),
        "pushed": pushed,
    }
    result_path = Path(os.environ.get("MARK_RESULT", "mark_result.json"))
    result_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": out["status"], "ids": out["ids"], "pushed": out["pushed"]}))
    return 0 if out["status"] in {"ok", "ignored", "empty", "disabled", "rejected"} else 1


if __name__ == "__main__":
    sys.exit(main())

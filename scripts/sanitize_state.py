"""Build a public tracker snapshot with listings, ids, and statuses only.

Contact names, profile URLs, notes, emails, and phone numbers are removed.
The source directory is never modified. The destination must be outside the
dashboard repository. This does not upload anything.
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import REPO_ROOT

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PROFILE_RE = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/[^\s\"'\\<>]+", re.I)
PHONE_RE = re.compile(r"(?<![\w/])(?:\+\d{1,3}[\s.\-]?)?(?:\(?\d{2,4}\)?[\s.\-]?)?\d{3,4}[\s.\-]\d{3,4}(?:[\s.\-]\d{2,4})?(?![\w])")
TOKEN_RE = re.compile(r"(?:ghp_|github_pat_|gho_|xox[baprs]-|bot\d+:)[A-Za-z0-9_\-]+")

LISTING_KEYS = {
    "_exp_max", "_exp_min", "applied_at", "company", "dashboard_visible", "date_posted",
    "exp_years", "experience_fit", "hide_reason", "job_id", "job_title", "link",
    "location", "referral", "relocation", "skipped_at", "source", "status", "stretch",
    "technical_fit", "visa_sponsorship", "why_fits",
}
DROP_KEYS = {
    "contacts", "notes", "note", "profile_url", "phone", "email", "reason",
    "name", "title", "first_message_at", "last_message_at", "reminder_at",
    "messages_sent", "reminders_sent", "cv_attached", "do_not_message",
    "counts_as_connection", "replied",
}


def _scrub(value):
    if not isinstance(value, str):
        return value
    text = PROFILE_RE.sub("", value)
    text = EMAIL_RE.sub("", text)
    text = PHONE_RE.sub("", text)
    text = TOKEN_RE.sub("", text)
    return text


def public_referral(referral) -> dict:
    referral = referral if isinstance(referral, dict) else {}
    return {
        "status": _scrub(referral.get("status") or "none"),
        "contacts": [],
        "updated_at": _scrub(referral.get("updated_at")),
    }


def sanitize_job(job: dict) -> dict:
    out = {}
    for key, value in job.items():
        if key not in LISTING_KEYS or key in DROP_KEYS:
            continue
        if key == "referral":
            out[key] = public_referral(value)
        else:
            out[key] = _scrub(value)
    out["referral"] = public_referral(job.get("referral"))
    return out


def sanitize_tracked(data: dict) -> dict:
    jobs = [sanitize_job(job) for job in data.get("all_jobs") or []]
    return {
        "seen_keys": list(data.get("seen_keys") or []),
        "all_jobs": jobs,
        "applied": list(data.get("applied") or []),
        "skipped": list(data.get("skipped") or []),
        "next_id": data.get("next_id"),
    }


def sanitize_applied(rows) -> list:
    out = []
    for row in rows or []:
        if not isinstance(row, dict) or not row.get("job_id"):
            continue
        out.append({"job_id": _scrub(row.get("job_id")), "applied_at": _scrub(row.get("applied_at"))})
    return out


def sanitize_skipped(rows) -> list:
    out = []
    for row in rows or []:
        if not isinstance(row, dict) or not row.get("job_id"):
            continue
        item = {"job_id": _scrub(row.get("job_id"))}
        if row.get("action"):
            item["action"] = _scrub(row.get("action"))
        if row.get("skipped_at"):
            item["skipped_at"] = _scrub(row.get("skipped_at"))
        if row.get("unskipped_at"):
            item["unskipped_at"] = _scrub(row.get("unskipped_at"))
        out.append(item)
    return out


def sanitize_referrals(rows) -> list:
    out = []
    for row in rows or []:
        if not isinstance(row, dict) or not row.get("job_id"):
            continue
        item = {
            "job_id": _scrub(row.get("job_id")),
            "status": _scrub(row.get("status") or "none"),
            "contacts": [],
            "updated_at": _scrub(row.get("updated_at")),
        }
        if row.get("source"):
            item["source"] = _scrub(row.get("source"))
        if isinstance(row.get("applied"), bool):
            item["applied"] = row["applied"]
        out.append(item)
    return out


def overlay_private(local: dict, public: dict) -> dict:
    """Operational fields come from the public snapshot. Contact history stays local."""
    local_jobs = {job.get("job_id"): job for job in local.get("all_jobs") or []}
    merged_jobs = []
    seen = set()
    for job in public.get("all_jobs") or []:
        job_id = job.get("job_id")
        seen.add(job_id)
        item = dict(job)
        previous = local_jobs.get(job_id)
        referral = dict(item.get("referral") or {})
        if previous:
            old = previous.get("referral") or {}
            referral["contacts"] = list(old.get("contacts") or [])
            if old.get("notes"):
                referral["notes"] = old.get("notes")
        else:
            referral["contacts"] = []
        item["referral"] = referral
        merged_jobs.append(item)
    for job_id, previous in local_jobs.items():
        if job_id not in seen:
            merged_jobs.append(previous)
    result = dict(local)
    result["all_jobs"] = merged_jobs
    if "applied" in public:
        result["applied"] = list(public.get("applied") or [])
    if "skipped" in public:
        result["skipped"] = list(public.get("skipped") or [])
    if public.get("next_id") is not None:
        result["next_id"] = public.get("next_id")
    if "seen_keys" in public:
        result["seen_keys"] = list(public.get("seen_keys") or [])
    return result


def audit_bytes(raw: bytes) -> dict:
    text = raw.decode("utf-8", errors="replace")
    return {
        "linkedin_profiles": len(PROFILE_RE.findall(text)),
        "emails": len(EMAIL_RE.findall(text)),
        "phones": len(PHONE_RE.findall(text)),
        "tokens": len(TOKEN_RE.findall(text)),
    }


def audit_tree(root: Path) -> dict:
    """Return counts only. Does not return matched text."""
    counts = {"linkedin_profiles": 0, "emails": 0, "phones": 0, "tokens": 0, "nonempty_contacts": 0, "forbidden_keys": 0}
    for path in sorted(root.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        counts["linkedin_profiles"] += len(PROFILE_RE.findall(text))
        counts["emails"] += len(EMAIL_RE.findall(text))
        counts["phones"] += len(PHONE_RE.findall(text))
        counts["tokens"] += len(TOKEN_RE.findall(text))
        data = json.loads(text)
        _walk(data, counts)
    return counts


def _walk(node, counts):
    if isinstance(node, dict):
        contacts = node.get("contacts")
        if isinstance(contacts, list) and contacts:
            counts["nonempty_contacts"] += 1
        for key, value in node.items():
            if key in DROP_KEYS and key != "contacts" and value not in (None, "", [], {}):
                counts["forbidden_keys"] += 1
            _walk(value, counts)
    elif isinstance(node, list):
        for item in node:
            _walk(item, counts)


def _load(path: Path, default):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8") or "null")


def export_sanitized(src: Path, dest: Path) -> dict:
    src = Path(src).resolve()
    dest = Path(dest).resolve()
    if dest == src or src in dest.parents or dest in src.parents:
        raise SystemExit("refusing to write the export over the source")
    if dest == REPO_ROOT or REPO_ROOT in dest.parents:
        raise SystemExit("refusing to write the export inside the dashboard repository")
    dest.mkdir(parents=True, exist_ok=True)
    tracked = sanitize_tracked(_load(src / "tracked_jobs.json", {}))
    applied = sanitize_applied(_load(src / "applied_updates.json", []))
    skipped = sanitize_skipped(_load(src / "skipped_updates.json", []))
    referrals = sanitize_referrals(_load(src / "referral_updates.json", []))
    files = {
        "tracked_jobs.json": tracked,
        "applied_updates.json": applied,
        "skipped_updates.json": skipped,
        "referral_updates.json": referrals,
    }
    for name, payload in files.items():
        (dest / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name in ("cron_state.json", "auto_referral_state.json", "direct_apply_companies.json"):
        source = src / name
        if not source.is_file():
            continue
        raw = source.read_bytes()
        if any(audit_bytes(raw).values()):
            continue
        (dest / name).write_bytes(raw)
    return {
        "jobs": len(tracked["all_jobs"]),
        "applied": len(tracked["applied"]),
        "skipped": len(tracked["skipped"]),
        "referral_rows": len(referrals),
        "audit": audit_tree(dest),
    }


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print("usage: sanitize_state.py SRC DEST")
        return 2
    summary = export_sanitized(Path(argv[0]), Path(argv[1]))
    print(json.dumps({"ok": True, "jobs": summary["jobs"], "applied": summary["applied"], "skipped": summary["skipped"], "audit": summary["audit"]}))
    return 0 if all(value == 0 for value in summary["audit"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())

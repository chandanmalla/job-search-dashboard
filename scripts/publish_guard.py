"""Refuse a dashboard publish that drops applied/skipped history or referral state."""
import json
import re


def extract_db_ids(html: str, name: str) -> list:
    match = re.search(rf"const {name} = (\[.*?\]);", html, re.S)
    if not match:
        raise ValueError(f"missing {name} in dashboard HTML")
    data = json.loads(match.group(1))
    if not isinstance(data, list):
        raise ValueError(f"{name} is not a list")
    return data


def job_map(text: str) -> dict:
    data = json.loads(text or "[]")
    if isinstance(data, dict):
        data = data.get("all_jobs") or data.get("jobs") or []
    out = {}
    for job in data:
        key = job.get("id") or job.get("job_id")
        if key:
            out[str(key)] = job
    return out


def _status(job) -> str:
    referral = job.get("referral") or {}
    status = referral.get("status")
    return status or "none"


def public_referral(referral) -> dict:
    """Status only. Contact names, notes, profile URLs, and phone fields stay private."""
    referral = referral if isinstance(referral, dict) else {}
    return {
        "status": referral.get("status") or "none",
        "contacts": [],
        "updated_at": referral.get("updated_at"),
    }


def clamp_jobs(jobs: list) -> list:
    clamped = []
    for job in jobs:
        item = dict(job)
        item["referral"] = public_referral(item.get("referral"))
        clamped.append(item)
    return clamped


def clamp_jobs_json(text: str) -> str:
    data = json.loads(text or "[]")
    if isinstance(data, dict):
        rows = data.get("all_jobs") or data.get("jobs") or []
        data = rows
    return json.dumps(clamp_jobs(data), ensure_ascii=False, indent=2) + "\n"


def clamp_html(html: str) -> str:
    match = re.search(
        r'(<script id="jobs-data" type="application/json">)(\[.*?\])(</script>)',
        html,
        re.S,
    )
    if not match:
        return html
    raw = match.group(2).replace("<\\/", "</")
    clamped = json.dumps(clamp_jobs(json.loads(raw)), ensure_ascii=False).replace("</", "<\\/")
    return html[: match.start(2)] + clamped + html[match.end(2) :]


def history_errors(old_html, new_html, old_jobs_text, new_jobs_text, *,
                   allow_needed=False, allow_new_jobs=False, referred_ids=()):
    """Return human-readable violations. Empty means the publish may proceed.

    Applied and skipped id sets are monotonic. An existing referral status of
    apply_direct, referred, requested, or skipped cannot change. `none` may
    become `needed` only when allow_needed is set (crawl auto-flag). A referred
    mark may set status to referred for an id in referred_ids.
    """
    errors = []
    try:
        old_applied = set(extract_db_ids(old_html, "DB_APPLIED"))
        new_applied = set(extract_db_ids(new_html, "DB_APPLIED"))
        old_skipped = set(extract_db_ids(old_html, "DB_SKIPPED"))
        new_skipped = set(extract_db_ids(new_html, "DB_SKIPPED"))
    except (ValueError, json.JSONDecodeError) as exc:
        return [str(exc)]
    lost_applied = sorted(old_applied - new_applied)
    lost_skipped = sorted(old_skipped - new_skipped)
    if lost_applied:
        errors.append(f"DB_APPLIED lost {len(lost_applied)} ids: {lost_applied[:8]}")
    if lost_skipped:
        errors.append(f"DB_SKIPPED lost {len(lost_skipped)} ids: {lost_skipped[:8]}")
    try:
        old_jobs = job_map(old_jobs_text)
        new_jobs = job_map(new_jobs_text)
    except json.JSONDecodeError as exc:
        return errors + [f"jobs.json is not valid JSON: {exc}"]
    if not allow_new_jobs:
        added = sorted(set(new_jobs) - set(old_jobs))
        removed = sorted(set(old_jobs) - set(new_jobs))
        if added:
            errors.append(f"jobs.json gained ids during applied-sync: {added[:8]}")
        if removed:
            errors.append(f"jobs.json lost ids: {removed[:8]}")
    referred = {str(i).upper() for i in referred_ids}
    for job_id, job in old_jobs.items():
        if job_id not in new_jobs:
            continue
        old_status = _status(job)
        new_status = _status(new_jobs[job_id])
        if old_status == new_status:
            continue
        if allow_needed and old_status == "none" and new_status == "needed":
            continue
        if new_status == "referred" and str(job_id).upper() in referred:
            continue
        errors.append(f"referral status changed for {job_id}: {old_status} -> {new_status}")
    return errors


def restore_if_unsafe(index_path, jobs_path, old_html, old_jobs, **kwargs):
    """If the new files violate history rules, put the previous bytes back."""
    new_html = index_path.read_text(encoding="utf-8")
    new_jobs = jobs_path.read_text(encoding="utf-8")
    errors = history_errors(old_html, new_html, old_jobs, new_jobs, **kwargs)
    if errors:
        index_path.write_text(old_html, encoding="utf-8")
        jobs_path.write_text(old_jobs, encoding="utf-8")
    return errors

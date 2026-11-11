"""Privacy boundary, even-IST schedule, and private-state merge checks.

The private bundle is optional. When it is absent the live test is skipped.
Assertions use hashes and counts. They do not print record contents.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import job_filters
import publish_guard
import schedule
import state_store
from git_publish import GitPublisher, PublishRefused

PRIVATE = Path("/tmp/jt-private")


def _logical(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class ScheduleTests(unittest.TestCase):
    def test_even_ist_hours_and_disabled_workflow(self):
        hours = schedule.ist_hours()
        self.assertEqual(sorted(hour for hour, minute in hours), [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22])
        self.assertTrue(all(minute == 0 for _hour, minute in hours))
        by_utc = dict(zip(schedule.utc_hours(), hours))
        self.assertEqual(by_utc[18], (0, 0))
        self.assertEqual(by_utc[0], (6, 0))
        odd = schedule.ist_hours("30 1,3,5,7,9,11,13,15,17,19,21,23 * * *")
        self.assertTrue(all(hour % 2 == 1 for hour, _minute in odd))
        workflow = (ROOT / ".github/workflows/crawl.yml").read_text(encoding="utf-8")
        active = "\n".join(line for line in workflow.splitlines() if not line.lstrip().startswith("#"))
        self.assertNotIn("schedule:", active)
        self.assertIn(schedule.EVEN_IST_CRON, workflow)


class PublishBoundaryTests(unittest.TestCase):
    def test_public_projection_drops_contacts_and_keeps_status(self):
        private = [{
            "id": "J1",
            "company": "Example",
            "title": "Senior Data Scientist",
            "referral": {
                "status": "needed",
                "contacts": [{
                    "name": "Pat Example",
                    "profile_url": "https://example.com/in/pat",
                    "notes": "synthetic note",
                }],
                "updated_at": "2026-11-01T00:00+05:30",
            },
        }]
        original = json.dumps(private)
        public = json.loads(publish_guard.clamp_jobs_json(json.dumps(private)))
        self.assertEqual(public[0]["referral"]["status"], "needed")
        self.assertEqual(public[0]["referral"]["contacts"], [])
        self.assertNotIn("synthetic note", json.dumps(public))
        self.assertEqual(json.dumps(private), original)

    def test_refuses_private_filenames(self):
        root = Path(tempfile.mkdtemp(prefix="gitsec-", dir="/tmp"))
        try:
            origin = root / "origin.git"
            clone = root / "clone"
            subprocess.check_call(["git", "init", "--bare", "-b", "main", str(origin)], stdout=subprocess.DEVNULL)
            subprocess.check_call(["git", "clone", str(origin), str(clone)], stdout=subprocess.DEVNULL)
            subprocess.check_call(["git", "config", "user.email", "test@example.com"], cwd=clone)
            subprocess.check_call(["git", "config", "user.name", "test"], cwd=clone)
            (clone / "readme.txt").write_text("ok\n", encoding="utf-8")
            subprocess.check_call(["git", "add", "readme.txt"], cwd=clone)
            subprocess.check_call(["git", "commit", "-m", "init"], cwd=clone, stdout=subprocess.DEVNULL)
            subprocess.check_call(["git", "push", "origin", "main"], cwd=clone, stdout=subprocess.DEVNULL)
            with self.assertRaises(PublishRefused):
                GitPublisher(clone, allow_reset=True).sync_publish(
                    ["tracked_jobs.json"], "no", lambda: None,
                )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_absent_private_repo_is_a_noop(self):
        previous = {key: os.environ.pop(key, None) for key in ("STATE_REPO", "STATE_REPO_TOKEN")}
        try:
            self.assertEqual(state_store.prepare(), 0)
        finally:
            for key, value in previous.items():
                if value is not None:
                    os.environ[key] = value


class FilterBehaviorTests(unittest.TestCase):
    def test_copied_filters_match_the_stated_rules(self):
        self.assertTrue(job_filters.title_ok("Senior Data Scientist"))
        self.assertTrue(job_filters.title_ok("Data Scientist III"))
        self.assertFalse(job_filters.title_ok("Data Scientist"))
        self.assertFalse(job_filters.title_ok("Data Scientist II"))
        self.assertTrue(job_filters.exp_ok(3, 7))
        self.assertFalse(job_filters.exp_ok(8, 10))
        self.assertFalse(job_filters.exp_ok(1, 2))
        self.assertFalse(job_filters.location_ok("Singapore"))
        self.assertFalse(job_filters.location_ok("Pune, India"))
        self.assertTrue(job_filters.location_ok("Bengaluru, India"))
        self.assertTrue(job_filters.location_ok("Bengaluru / Pune"))
        self.assertFalse(job_filters.company_product("Infosys"))
        self.assertTrue(job_filters.company_product("Example Labs"))
        self.assertFalse(job_filters.company_excluded("Example Labs"))
        self.assertTrue(job_filters.company_excluded("McKinsey"))
        self.assertTrue(job_filters.company_excluded("Bain & Company"))
        for name in (
            "Deloitte", "Deloitte Consulting", "Deloitte India",
            "EY", "E&Y", "Ernst & Young", "Ernst and Young",
            "KPMG", "PwC", "PricewaterhouseCoopers",
        ):
            self.assertTrue(job_filters.is_big4(name), name)
            self.assertFalse(job_filters.company_excluded(name), name)
            self.assertFalse(job_filters.company_non_product(name), name)
            self.assertTrue(job_filters.company_product(name), name)
            self.assertTrue(job_filters.company_top(name), name)
        visible, reason = job_filters.visibility({
            "company": "Deloitte",
            "job_title": "Senior Data Scientist",
            "location": "Bengaluru, India",
            "status": "",
        })
        self.assertTrue(visible, reason)


class PrivateMergeTests(unittest.TestCase):
    def test_bundle_merge_preserves_state_and_second_run_is_quiet(self):
        if not (PRIVATE / "tracked_jobs.json").is_file():
            self.skipTest("private bundle is not on this machine")
        work = Path(tempfile.mkdtemp(prefix="jt-merge-", dir="/tmp"))
        try:
            for name in (
                "tracked_jobs.json", "applied_updates.json", "skipped_updates.json",
                "referral_updates.json", "cron_state.json", "auto_referral_state.json",
                "referral_other_allowlist.json",
            ):
                shutil.copy2(PRIVATE / name, work / name)
            before_logical = _logical(work / "tracked_jobs.json")
            before_bytes = (work / "tracked_jobs.json").read_bytes()
            env = dict(os.environ)
            env["JT_DIR"] = str(work)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            first = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "merge_referral_updates.py")],
                cwd=work, env=env, capture_output=True, text=True,
            )
            self.assertEqual(first.returncode, 0)
            self.assertIn("rewritten=0", first.stdout)
            self.assertNotIn("linkedin", first.stdout.lower())
            self.assertEqual((work / "tracked_jobs.json").read_bytes(), before_bytes)
            self.assertEqual(_logical(work / "tracked_jobs.json"), before_logical)
            second = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "merge_referral_updates.py")],
                cwd=work, env=env, capture_output=True, text=True,
            )
            self.assertEqual(second.returncode, 0)
            self.assertIn("rewritten=0", second.stdout)
            self.assertEqual((work / "tracked_jobs.json").read_bytes(), before_bytes)
            referral = (work / "referral_updates.json").read_bytes()
            flagged = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "auto_referral_needed.py"), "--dry-run"],
                cwd=work, env=env, capture_output=True, text=True,
            )
            self.assertEqual(flagged.returncode, 0)
            if flagged.stdout.strip() != "[auto_ref] dry flagged=0":
                raise AssertionError("auto_ref did not report a zero count")
            self.assertEqual((work / "referral_updates.json").read_bytes(), referral)
        finally:
            shutil.rmtree(work, ignore_errors=True)


DIRECT_FILE = Path("/home/ubuntu/.cursor/projects/workspace/uploads/direct_apply_companies_26d9.json")
DIRECT_SHA = "a38043dfde8ab8fbb4e6f609473dfb97a9dc60e5607dd679a0e76a2e637332d3"


class DirectApplyTests(unittest.TestCase):
    def test_exact_file_and_merge_rules(self):
        if not DIRECT_FILE.is_file():
            self.skipTest("direct apply file not mounted")
        raw = DIRECT_FILE.read_bytes()
        self.assertEqual(len(raw), 236)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), DIRECT_SHA)
        names = json.loads(raw.decode("utf-8"))
        self.assertEqual(len(names), 15)
        self.assertTrue(all(isinstance(name, str) and name.strip() for name in names))
        listed = names[0]
        work = Path(tempfile.mkdtemp(prefix="direct-apply-", dir="/tmp"))
        try:
            (work / "direct_apply_companies.json").write_bytes(raw)
            (work / "referral_updates.json").write_text("[]\n", encoding="utf-8")
            (work / "applied_updates.json").write_text("[]\n", encoding="utf-8")
            (work / "skipped_updates.json").write_text("[]\n", encoding="utf-8")
            tracked = {
                "all_jobs": [
                    {"job_id": "J1", "company": listed, "status": None, "dashboard_visible": True,
                     "referral": {"status": "none", "contacts": [{"name": "Synthetic"}], "updated_at": None}},
                    {"job_id": "J2", "company": listed, "status": "Applied", "dashboard_visible": True,
                     "referral": {"status": "none", "contacts": [], "updated_at": None}},
                    {"job_id": "J3", "company": listed, "status": None, "dashboard_visible": True,
                     "referral": {"status": "referred", "contacts": [{"name": "Keep"}], "updated_at": "2026-01-01T00:00+05:30"}},
                    {"job_id": "J4", "company": "Example Labs", "status": None, "dashboard_visible": True,
                     "referral": {"status": "none", "contacts": [], "updated_at": None}},
                    {"job_id": "J5", "company": listed, "status": None, "dashboard_visible": False,
                     "referral": {"status": "none", "contacts": [], "updated_at": None}},
                ],
                "applied": ["J2"],
                "skipped": [],
            }
            (work / "tracked_jobs.json").write_text(json.dumps(tracked), encoding="utf-8")
            env = dict(os.environ)
            env["JT_DIR"] = str(work)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            first = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "merge_referral_updates.py")],
                cwd=work, env=env, capture_output=True, text=True,
            )
            self.assertEqual(first.returncode, 0, "merge failed")
            after = json.loads((work / "tracked_jobs.json").read_text(encoding="utf-8"))
            by_id = {job["job_id"]: job for job in after["all_jobs"]}
            self.assertEqual(by_id["J1"]["referral"]["status"], "apply_direct")
            self.assertEqual(by_id["J1"]["referral"]["contacts"], [{"name": "Synthetic"}])
            self.assertNotEqual(by_id["J2"]["referral"]["status"], "apply_direct")
            self.assertEqual(by_id["J3"]["referral"]["status"], "referred")
            self.assertEqual(by_id["J3"]["referral"]["contacts"], [{"name": "Keep"}])
            self.assertEqual(by_id["J4"]["referral"]["status"], "none")
            self.assertEqual(by_id["J5"]["referral"]["status"], "none")
            self.assertEqual(after["applied"], ["J2"])
            stamped = (work / "tracked_jobs.json").read_bytes()
            second = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "merge_referral_updates.py")],
                cwd=work, env=env, capture_output=True, text=True,
            )
            self.assertEqual(second.returncode, 0)
            self.assertIn("rewritten=0", second.stdout)
            self.assertEqual((work / "tracked_jobs.json").read_bytes(), stamped)
            self.assertEqual((work / "direct_apply_companies.json").read_bytes(), raw)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_private_preflight_does_not_publish_or_rewrite(self):
        if not (PRIVATE / "tracked_jobs.json").is_file() or not DIRECT_FILE.is_file():
            self.skipTest("private bundle or direct apply file not mounted")
        work = Path(tempfile.mkdtemp(prefix="jt-preflight-", dir="/tmp"))
        try:
            for name in (
                "tracked_jobs.json", "applied_updates.json", "skipped_updates.json",
                "referral_updates.json", "cron_state.json",
            ):
                shutil.copy2(PRIVATE / name, work / name)
            (work / "direct_apply_companies.json").write_bytes(DIRECT_FILE.read_bytes())
            before = (work / "tracked_jobs.json").read_bytes()
            env = dict(os.environ)
            env["JT_DIR"] = str(work)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "hosted_runner.py"), "--mode", "preflight"],
                cwd=ROOT, env=env, capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            self.assertTrue(report["ok"])
            self.assertEqual(report["missing_files"], [])
            self.assertNotIn("publish", report)
            self.assertEqual((work / "tracked_jobs.json").read_bytes(), before)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_real_state_direct_apply_preserves_history(self):
        if not (PRIVATE / "tracked_jobs.json").is_file() or not DIRECT_FILE.is_file():
            self.skipTest("private bundle or direct apply file not mounted")
        work = Path(tempfile.mkdtemp(prefix="jt-direct-", dir="/tmp"))
        try:
            for name in (
                "tracked_jobs.json", "applied_updates.json", "skipped_updates.json",
                "referral_updates.json",
            ):
                shutil.copy2(PRIVATE / name, work / name)
            raw = DIRECT_FILE.read_bytes()
            (work / "direct_apply_companies.json").write_bytes(raw)
            before = json.loads((work / "tracked_jobs.json").read_text(encoding="utf-8"))

            def contact_digest(payload):
                rows = [
                    (job.get("job_id"), (job.get("referral") or {}).get("contacts"))
                    for job in payload["all_jobs"]
                ]
                return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()

            before_contacts = contact_digest(before)
            env = dict(os.environ)
            env["JT_DIR"] = str(work)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            first = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "merge_referral_updates.py")],
                cwd=work, env=env, capture_output=True, text=True,
            )
            self.assertEqual(first.returncode, 0, "merge failed")
            after = json.loads((work / "tracked_jobs.json").read_text(encoding="utf-8"))
            self.assertEqual(after.get("applied"), before.get("applied"))
            self.assertEqual(after.get("skipped"), before.get("skipped"))
            self.assertEqual(contact_digest(after), before_contacts)
            before_jobs = {job.get("job_id"): job for job in before["all_jobs"]}
            flips = 0
            for job in after["all_jobs"]:
                old = before_jobs[job.get("job_id")]
                old_status = ((old.get("referral") or {}).get("status") or "none")
                new_status = ((job.get("referral") or {}).get("status") or "none")
                if old_status == new_status:
                    continue
                self.assertEqual(old_status, "none")
                self.assertEqual(new_status, "apply_direct")
                flips += 1
            stamped = (work / "tracked_jobs.json").read_bytes()
            second = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "merge_referral_updates.py")],
                cwd=work, env=env, capture_output=True, text=True,
            )
            self.assertEqual(second.returncode, 0)
            self.assertIn("rewritten=0", second.stdout)
            self.assertEqual((work / "tracked_jobs.json").read_bytes(), stamped)
            self.assertEqual((work / "direct_apply_companies.json").read_bytes(), raw)
            self.assertGreaterEqual(flips, 0)
        finally:
            shutil.rmtree(work, ignore_errors=True)


class SanitizeTests(unittest.TestCase):
    def test_allowlist_drops_contacts_and_overlay_restores_them(self):
        import sanitize_state
        local = {
            "all_jobs": [{
                "job_id": "J1",
                "company": "Example",
                "job_title": "Senior Data Scientist",
                "location": "Bengaluru, India",
                "link": "https://example.com/jobs/1",
                "status": "Applied",
                "referral": {
                    "status": "referred",
                    "updated_at": "2026-11-01T00:00+05:30",
                    "notes": "synthetic note",
                    "contacts": [{
                        "name": "Pat Example",
                        "profile_url": "https://www.linkedin.com/in/pat-example",
                        "notes": "call tomorrow",
                        "phone": "+91 90000 00000",
                    }],
                },
                "private_blob": "should drop",
            }],
            "applied": ["J1"],
            "skipped": [],
            "seen_keys": ["example|senior data scientist"],
            "next_id": 2,
        }
        public = sanitize_state.sanitize_tracked(local)
        blob = json.dumps(public)
        self.assertNotIn("Pat Example", blob)
        self.assertNotIn("linkedin.com/in", blob)
        self.assertNotIn("synthetic note", blob)
        self.assertNotIn("90000", blob)
        self.assertNotIn("private_blob", blob)
        self.assertEqual(public["all_jobs"][0]["job_id"], "J1")
        self.assertEqual(public["all_jobs"][0]["company"], "Example")
        self.assertEqual(public["all_jobs"][0]["link"], "https://example.com/jobs/1")
        self.assertEqual(public["all_jobs"][0]["referral"]["status"], "referred")
        self.assertEqual(public["all_jobs"][0]["referral"]["contacts"], [])
        self.assertEqual(public["applied"], ["J1"])
        restored = sanitize_state.overlay_private(local, public)
        self.assertEqual(restored["all_jobs"][0]["referral"]["contacts"][0]["name"], "Pat Example")
        self.assertEqual(restored["all_jobs"][0]["referral"]["status"], "referred")
        public["all_jobs"][0]["referral"]["status"] = "needed"
        restored = sanitize_state.overlay_private(local, public)
        self.assertEqual(restored["all_jobs"][0]["referral"]["status"], "needed")
        self.assertEqual(restored["all_jobs"][0]["referral"]["contacts"][0]["profile_url"], "https://www.linkedin.com/in/pat-example")

    def test_real_export_statuses_match_and_audit_is_clean(self):
        import sanitize_state
        if not (PRIVATE / "tracked_jobs.json").is_file():
            self.skipTest("private bundle is not on this machine")
        dest = Path(tempfile.mkdtemp(prefix="jt-sanitized-", dir="/tmp"))
        try:
            before = (PRIVATE / "tracked_jobs.json").read_bytes()
            summary = sanitize_state.export_sanitized(PRIVATE, dest)
            self.assertEqual((PRIVATE / "tracked_jobs.json").read_bytes(), before)
            self.assertEqual(summary["audit"], {
                "linkedin_profiles": 0, "emails": 0, "phones": 0, "tokens": 0,
                "nonempty_contacts": 0, "forbidden_keys": 0,
            })
            src = json.loads(before.decode("utf-8"))
            dst = json.loads((dest / "tracked_jobs.json").read_text(encoding="utf-8"))
            self.assertEqual(
                [job.get("job_id") for job in src["all_jobs"]],
                [job.get("job_id") for job in dst["all_jobs"]],
            )
            self.assertEqual(src.get("applied"), dst.get("applied"))
            self.assertEqual(src.get("skipped"), dst.get("skipped"))
            src_status = [((job.get("referral") or {}).get("status") or "none") for job in src["all_jobs"]]
            dst_status = [((job.get("referral") or {}).get("status") or "none") for job in dst["all_jobs"]]
            self.assertEqual(src_status, dst_status)
            again = Path(tempfile.mkdtemp(prefix="jt-sanitized2-", dir="/tmp"))
            sanitize_state.export_sanitized(PRIVATE, again)
            for name in ("tracked_jobs.json", "applied_updates.json", "skipped_updates.json", "referral_updates.json"):
                self.assertEqual((dest / name).read_bytes(), (again / name).read_bytes())
            overlay = sanitize_state.overlay_private(src, dst)
            self.assertEqual(
                [(job.get("job_id"), (job.get("referral") or {}).get("contacts")) for job in src["all_jobs"]],
                [(job.get("job_id"), (job.get("referral") or {}).get("contacts")) for job in overlay["all_jobs"]],
            )
        finally:
            shutil.rmtree(dest, ignore_errors=True)


class MarkPrivacyTests(unittest.TestCase):
    def test_public_issue_body_has_no_note(self):
        import marks
        body = "<!-- dashboard-mark -->\napplied J123\nnote: call this person tomorrow\n"
        parsed = marks.parse_mark_text(body)
        safe = marks.safe_issue_body(parsed)
        self.assertIn("applied J123", safe)
        self.assertNotIn("tomorrow", safe)
        self.assertNotIn("call this person", safe)


if __name__ == "__main__":
    unittest.main()

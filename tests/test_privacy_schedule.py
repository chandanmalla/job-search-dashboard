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

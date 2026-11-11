"""Hosted pipeline tests. No network scraping. Canonical PC files are not synthesized."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import backup_state
import file_lock
import hosted_runner
import http_retry
import marks
import process_inbox
import publish_guard
import sweep_crawler
import updates_lib
from git_publish import GitPublisher, PublishRefused
from redact import redact

FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "nov8_115f06a.json").read_text(encoding="utf-8"))
REAL_INBOX = (ROOT / "data" / "applied_inbox.json").read_bytes()
REAL_JOBS = (ROOT / "data" / "jobs.json").read_bytes()
REAL_HTML = (ROOT / "index.html").read_bytes()


def _git(cwd, *args, check=True):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise AssertionError(f"git {args} failed: {result.stderr}")
    return result


class EnvCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hosted-"))
        self.jt = self.tmp / "jt"
        self.jt.mkdir()
        self.inbox = self.tmp / "applied_inbox.json"
        self._old = {key: os.environ.get(key) for key in ("JT_DIR", "INBOX_PATH", "MARK_RESULT")}
        os.environ["JT_DIR"] = str(self.jt)
        os.environ["INBOX_PATH"] = str(self.inbox)
        os.environ["MARK_RESULT"] = str(self.tmp / "mark_result.json")

    def tearDown(self):
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.assertEqual((ROOT / "data" / "applied_inbox.json").read_bytes(), REAL_INBOX)
        self.assertEqual((ROOT / "data" / "jobs.json").read_bytes(), REAL_JOBS)
        self.assertEqual((ROOT / "index.html").read_bytes(), REAL_HTML)


class Nov8Regression(EnvCase):
    def _seed_history(self):
        skipped = [{"job_id": job_id, "skipped_at": "2026-11-01T00:00+05:30"} for job_id in FIXTURE["skipped_before"]]
        referral = [
            {"job_id": "J001", "status": "referred", "contacts": [], "updated_at": "2026-10-01T00:00+05:30"},
            {"job_id": "J003", "status": "apply_direct", "contacts": [], "updated_at": "2026-10-01T00:00+05:30"},
        ]
        updates_lib.atomic_write_json(self.jt / "skipped_updates.json", skipped)
        updates_lib.atomic_write_json(self.jt / "referral_updates.json", referral)
        updates_lib.atomic_write_json(self.inbox, json.loads(json.dumps(FIXTURE["inbox"])))
        return skipped, referral

    def test_commit_115f06a_counts_and_idempotent_inbox(self):
        inbox = FIXTURE["inbox"]
        self.assertEqual(len(inbox), 49)
        days = {}
        for entry in inbox:
            days[entry["ts"][:10]] = days.get(entry["ts"][:10], 0) + 1
        self.assertEqual(days, {"2026-11-05": 20, "2026-11-08": 29})
        self.assertEqual(len(FIXTURE["applied_before"]), 433)
        self.assertEqual(len(FIXTURE["applied_after"]), 482)
        self.assertEqual(len(FIXTURE["skipped_before"]), 73)
        self.assertEqual(FIXTURE["skipped_before"], FIXTURE["skipped_after"])
        added = set(FIXTURE["applied_after"]) - set(FIXTURE["applied_before"])
        self.assertEqual(added, {entry["job_id"].upper() for entry in inbox})
        visible_before = set(FIXTURE["applied_before"]) & set(FIXTURE["job_ids_before"])
        visible_after = set(FIXTURE["applied_after"]) & set(FIXTURE["job_ids_after"])
        self.assertEqual(len(visible_before), 334)
        self.assertEqual(len(visible_after), 383)
        self.assertEqual(sorted(set(FIXTURE["job_ids_after"]) - set(FIXTURE["job_ids_before"])),
                         [f"J{n}" for n in range(646, 659)])

        skipped, referral = self._seed_history()
        self.assertEqual(process_inbox.main(), 0)
        applied = json.loads((self.jt / "applied_updates.json").read_text(encoding="utf-8"))
        self.assertEqual({row["job_id"] for row in applied}, added)
        self.assertEqual(len(applied), 49)
        self.assertEqual(json.loads((self.jt / "skipped_updates.json").read_text(encoding="utf-8")), skipped)
        self.assertEqual(json.loads((self.jt / "referral_updates.json").read_text(encoding="utf-8")), referral)
        self.assertEqual(json.loads(self.inbox.read_text(encoding="utf-8")), [])
        self.assertEqual(process_inbox.main(), 0)
        applied_again = json.loads((self.jt / "applied_updates.json").read_text(encoding="utf-8"))
        self.assertEqual(len(applied_again), 49)

    def test_duplicate_fingerprint_and_unknown_entry(self):
        self._seed_history()
        rows = json.loads(self.inbox.read_text(encoding="utf-8"))
        rows.append(dict(rows[0], ts="2026-11-08T00:00:00Z"))
        rows.append({"note": "keep me"})
        self.inbox.write_text(json.dumps(rows), encoding="utf-8")
        self.assertEqual(process_inbox.main(), 0)
        applied = json.loads((self.jt / "applied_updates.json").read_text(encoding="utf-8"))
        self.assertEqual(len(applied), 49)
        self.assertEqual(json.loads(self.inbox.read_text(encoding="utf-8")), [{"note": "keep me"}])

    def test_corrupt_updates_do_not_clear_inbox(self):
        self._seed_history()
        (self.jt / "applied_updates.json").write_text("{", encoding="utf-8")
        before = self.inbox.read_text(encoding="utf-8")
        self.assertEqual(process_inbox.main(), 1)
        self.assertEqual(self.inbox.read_text(encoding="utf-8"), before)

    def test_concurrent_writers_are_idempotent(self):
        self._seed_history()
        codes = []

        def run():
            codes.append(process_inbox.main())

        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(codes, [0, 0])
        applied = json.loads((self.jt / "applied_updates.json").read_text(encoding="utf-8"))
        self.assertEqual(len(applied), 49)
        self.assertEqual(len({row["job_id"] for row in applied}), 49)
        self.assertEqual(json.loads(self.inbox.read_text(encoding="utf-8")), [])


class PipelineBoundaries(EnvCase):
    def test_bundle_is_not_vendored(self):
        canonical = ROOT / "state" / "job-tracker"
        for name in ("tracked_jobs.json", "job_filters.py", "merge_referral_updates.py",
                     "auto_referral_needed.py", "applied_updates.json", "config.json"):
            self.assertFalse((canonical / name).exists(), name)

    def test_applied_sync_plan_has_no_side_effects(self):
        text = " ".join(hosted_runner.commands("applied-sync"))
        for banned in ("sweep", "telegram", "outreach", "auto_referral", "generate_report"):
            self.assertNotIn(banned, text)
        crawl = " ".join(hosted_runner.commands("crawl"))
        self.assertIn("sweep_crawler.py", crawl)
        self.assertIn("--no-telegram", crawl)
        self.assertNotIn("outreach", crawl)
        self.assertNotIn("sync_applied_from_telegram", crawl)
        notified = " ".join(hosted_runner.commands("crawl", notifications=True, outreach=True, telegram_sync=True))
        self.assertNotIn("--no-telegram", notified)
        self.assertIn("outreach_queue.py", notified)
        self.assertIn("sync_applied_from_telegram.py", notified)

    def test_applied_sync_refuses_notifications_and_missing_state(self):
        self.inbox.write_text(json.dumps(FIXTURE["inbox"][:2]), encoding="utf-8")
        refused = hosted_runner.execute("applied-sync", notifications=True)
        self.assertFalse(refused["ok"])
        self.assertEqual(json.loads(self.inbox.read_text(encoding="utf-8"))[0]["job_id"], "J359")
        report = hosted_runner.execute("applied-sync")
        self.assertFalse(report["ok"])
        self.assertIn("tracked_jobs.json", report["missing_files"])
        self.assertIn("referral_updates.json", report["missing_files"])
        self.assertNotIn("job_filters.py", report["missing_files"])
        self.assertTrue(any(step["name"] == "sweep_crawler" and step["status"] == "skipped" for step in report["steps"]))
        self.assertTrue(any(step["name"] == "telegram" and step["status"] == "skipped" for step in report["steps"]))
        self.assertEqual(len(json.loads(self.inbox.read_text(encoding="utf-8"))), 2)
        self.assertFalse((self.jt / "applied_updates.json").exists())

    def test_preflight_does_not_write_health(self):
        health = ROOT / "state" / "health.json"
        before = health.read_bytes() if health.exists() else None
        report = hosted_runner.execute("preflight")
        self.assertFalse(report["ok"])
        after = health.read_bytes() if health.exists() else None
        self.assertEqual(before, after)

    def test_backup_keeps_five(self):
        updates_lib.atomic_write_json(self.jt / "tracked_jobs.json", {"all_jobs": []})
        for index in range(7):
            backup_state.backup_state(self.jt, stamp=f"20261108T00000{index}Z")
        stamps = sorted(path.name for path in (self.jt / "backups").iterdir())
        self.assertEqual(len(stamps), 5)
        self.assertEqual(stamps[0], "20261108T000002Z")


class PublishGuardTests(unittest.TestCase):
    def _html(self, applied, skipped):
        return f"<script>const DB_APPLIED = {json.dumps(applied)};\nconst DB_SKIPPED = {json.dumps(skipped)};</script>"

    def test_drops_and_referral_policy_restore(self):
        old_jobs = json.dumps([
            {"id": "J1", "referral": {"status": "apply_direct"}},
            {"id": "J2", "referral": {"status": "none"}},
            {"id": "J3", "referral": {"status": "needed"}},
        ])
        new_jobs = json.dumps([
            {"id": "J1", "referral": {"status": "needed"}},
            {"id": "J2", "referral": {"status": "requested"}},
            {"id": "J3", "referral": {"status": "needed"}},
            {"id": "J9", "referral": {"status": "none"}},
        ])
        errors = publish_guard.history_errors(
            self._html(["J1"], ["J3"]),
            self._html(["J1"], []),
            old_jobs, new_jobs, allow_needed=True, allow_new_jobs=True,
        )
        self.assertTrue(any("DB_SKIPPED" in error for error in errors))
        self.assertTrue(any("apply_direct" in error for error in errors))
        self.assertTrue(any("requested" in error for error in errors))
        allowed = publish_guard.history_errors(
            self._html(["J1"], ["J3"]),
            self._html(["J1", "J2"], ["J3"]),
            old_jobs,
            json.dumps([
                {"id": "J1", "referral": {"status": "apply_direct"}},
                {"id": "J2", "referral": {"status": "needed"}},
                {"id": "J3", "referral": {"status": "needed"}},
            ]),
            allow_needed=True, allow_new_jobs=True,
        )
        self.assertEqual(allowed, [])
        blocked = publish_guard.history_errors(
            self._html(["J1"], ["J3"]),
            self._html(["J1"], ["J3"]),
            old_jobs,
            json.dumps([
                {"id": "J1", "referral": {"status": "apply_direct"}},
                {"id": "J2", "referral": {"status": "needed"}},
                {"id": "J3", "referral": {"status": "needed"}},
            ]),
            allow_needed=False, allow_new_jobs=False,
        )
        self.assertTrue(any("needed" in error for error in blocked))

    def test_restore_writes_previous_bytes(self):
        directory = Path(tempfile.mkdtemp(prefix="guard-"))
        try:
            index = directory / "index.html"
            jobs = directory / "jobs.json"
            old_html = self._html(["J1"], ["J9"])
            old_jobs = json.dumps([{"id": "J1", "referral": {"status": "apply_direct"}}])
            index.write_text(self._html([], ["J9"]), encoding="utf-8")
            jobs.write_text(old_jobs, encoding="utf-8")
            errors = publish_guard.restore_if_unsafe(index, jobs, old_html, old_jobs)
            self.assertTrue(errors)
            self.assertEqual(index.read_text(encoding="utf-8"), old_html)
            self.assertEqual(jobs.read_text(encoding="utf-8"), old_jobs)
        finally:
            shutil.rmtree(directory)


class HttpAndSecrets(unittest.TestCase):
    def test_backoff_is_bounded_and_skips_other_codes(self):
        headers = Message()
        headers["Retry-After"] = "100"
        waits = []

        def opener():
            opener.n += 1
            if opener.n < 3:
                raise urllib.error.HTTPError("http://example.test", 429, "rate", headers, None)
            return "ok"

        opener.n = 0
        result = http_retry.urlopen_retry(opener, max_retries=4, sleep=waits.append, cap=20, base=1)
        self.assertEqual(result, "ok")
        self.assertEqual(waits, [20, 20])

        def rejected():
            raise urllib.error.HTTPError("http://example.test", 400, "no", Message(), None)

        with self.assertRaises(urllib.error.HTTPError):
            http_retry.urlopen_retry(rejected, sleep=lambda _s: (_ for _ in ()).throw(AssertionError("slept")))

    def test_redact_tokens(self):
        text = redact("failed https://api.telegram.org/bot123456:ABCDEFghijklmnop/sendMessage and ghp_abcdefghijklmnopqrstuvwxyz123456")
        self.assertNotIn("ABCDEFghijklmnop", text)
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz123456", text)
        self.assertIn("<redacted>", text)

    def test_loading_filters_does_not_open_the_network(self):
        calls = []
        original = urllib.request.urlopen
        urllib.request.urlopen = lambda *args, **kwargs: calls.append(args)
        previous = os.environ.get("JT_DIR")
        temporary = tempfile.mkdtemp(prefix="nofilt-")
        os.environ["JT_DIR"] = temporary
        try:
            sweep_crawler._bind_paths()
            self.assertIsNotNone(sweep_crawler.JF)
            self.assertEqual(calls, [])
        finally:
            urllib.request.urlopen = original
            if previous is None:
                os.environ.pop("JT_DIR", None)
            else:
                os.environ["JT_DIR"] = previous
            shutil.rmtree(temporary, ignore_errors=True)


class MarkAuth(EnvCase):
    def test_allow_list_and_token_rejection(self):
        self.assertTrue(marks.author_allowed("ChandanMalla", None))
        self.assertFalse(marks.author_allowed("someoneelse", None))
        with self.assertRaises(ValueError):
            marks.parse_mark_text("<!-- dashboard-mark -->\napplied J123\nghp_abcdefghijklmnopqrstuvwxyz123456\n")
        parsed = marks.parse_mark_text("<!-- dashboard-mark -->\napplied J123\nskipped J9\nreferred J123\n")
        self.assertEqual(parsed, [
            {"job_id": "J123", "action": "applied"},
            {"job_id": "J9", "action": "skipped"},
            {"job_id": "J123", "action": "referred"},
        ])
        disabled = marks.handle_issue(
            actor="chandanmalla", authors=None, title="Dashboard marks",
            body="<!-- dashboard-mark -->\napplied J123\n", enabled=False, ts="2026-11-08T00:00:00Z",
        )
        self.assertEqual(disabled["status"], "disabled")
        self.assertFalse(self.inbox.exists())
        stranger = marks.handle_issue(
            actor="someoneelse", authors=None, title="Dashboard marks",
            body="<!-- dashboard-mark -->\napplied J1\n", enabled=True, ts="2026-11-08T00:00:00Z",
        )
        self.assertEqual(stranger["status"], "rejected")
        self.assertFalse(self.inbox.exists())
        accepted = marks.handle_issue(
            actor="chandanmalla", authors=None, title="Dashboard marks",
            body="<!-- dashboard-mark -->\napplied J123\n", enabled=True, ts="2026-11-08T00:00:00Z",
        )
        self.assertEqual(accepted["status"], "ok")
        again = marks.handle_issue(
            actor="chandanmalla", authors=None, title="Dashboard marks",
            body="<!-- dashboard-mark -->\napplied J123\n", enabled=True, ts="2026-11-08T00:00:00Z",
        )
        self.assertEqual(again["status"], "ok")
        rows = json.loads(self.inbox.read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 1)

    def test_dashboard_template_mentions_login_sync(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        source = (ROOT / "build_site.py").read_text(encoding="utf-8")
        self.assertIn("btnGithubLogin", html)
        self.assertIn("btnGithubLogin", source)
        self.assertIn("DB_APPLIED", html)
        self.assertIn("DB_SKIPPED", html)


class GitRetry(unittest.TestCase):
    def test_rejected_push_replays_and_keeps_both_sides(self):
        root = Path(tempfile.mkdtemp(prefix="gitpub-"))
        try:
            origin = root / "origin.git"
            left = root / "left"
            right = root / "right"
            _git(root, "init", "--bare", "-b", "main", str(origin))
            _git(root, "clone", str(origin), str(left))
            _git(left, "config", "user.email", "test@example.com")
            _git(left, "config", "user.name", "test")
            (left / "data").mkdir()
            (left / "data" / "note.json").write_text("[]\n", encoding="utf-8")
            _git(left, "add", "data/note.json")
            _git(left, "commit", "-m", "init")
            _git(left, "push", "origin", "main")
            _git(root, "clone", str(origin), str(right))
            state = {"n": 0}

            def mutate():
                path = right / "data" / "note.json"
                current = json.loads(path.read_text(encoding="utf-8"))
                if state["n"] == 0:
                    state["n"] = 1
                    other = left / "data" / "note.json"
                    other.write_text(json.dumps(["A"]) + "\n", encoding="utf-8")
                    _git(left, "add", "data/note.json")
                    _git(left, "commit", "-m", "A")
                    _git(left, "push", "origin", "main")
                if "B" not in current:
                    current.append("B")
                path.write_text(json.dumps(current) + "\n", encoding="utf-8")

            published = GitPublisher(right, allow_reset=True).sync_publish(
                ["data/note.json"], "B", mutate,
            )
            self.assertTrue(published["ok"])
            self.assertGreaterEqual(published["attempts"], 2)
            final = json.loads((right / "data" / "note.json").read_text(encoding="utf-8"))
            self.assertEqual(final, ["A", "B"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_refuses_secret_paths(self):
        root = Path(tempfile.mkdtemp(prefix="gitsec-"))
        try:
            origin = root / "origin.git"
            clone = root / "clone"
            _git(root, "init", "--bare", "-b", "main", str(origin))
            _git(root, "clone", str(origin), str(clone))
            _git(clone, "config", "user.email", "test@example.com")
            _git(clone, "config", "user.name", "test")
            (clone / "readme.txt").write_text("ok\n", encoding="utf-8")
            _git(clone, "add", "readme.txt")
            _git(clone, "commit", "-m", "init")
            _git(clone, "push", "origin", "main")

            def mutate():
                (clone / "config.json").write_text("{}\n", encoding="utf-8")

            with self.assertRaises(PublishRefused):
                GitPublisher(clone, allow_reset=True).sync_publish(
                    ["config.json"], "no", mutate,
                )
            listed = _git(origin, "ls-tree", "-r", "--name-only", "HEAD")
            self.assertNotIn("config.json", listed.stdout)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class LockSmoke(unittest.TestCase):
    def test_reentrant_lock(self):
        directory = Path(tempfile.mkdtemp(prefix="lock-"))
        try:
            with file_lock.state_lock(directory):
                with file_lock.state_lock(directory):
                    self.assertTrue((directory / ".write.lock").exists())
        finally:
            shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

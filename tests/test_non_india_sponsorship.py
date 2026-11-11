"""Outside India, keep a job only with sponsorship text or an allowlisted company."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import job_filters as JF


def job(company, location, title="Senior Data Scientist", description="", status="", referral="none"):
    return {
        "job_id": "J1",
        "company": company,
        "job_title": title,
        "location": location,
        "_desc": description,
        "status": status,
        "referral": {"status": referral, "contacts": []},
    }


class NonIndiaSponsorshipTests(unittest.TestCase):
    def test_keep_when_posting_states_sponsorship(self):
        row = job("Example Labs", "London, United Kingdom", description="Visa sponsorship available for this role.")
        self.assertFalse(JF.hide_open_non_india(row))
        self.assertTrue(JF.visibility(row, require_top=False)[0])

    def test_keep_when_company_is_allowlisted(self):
        row = job("Wise", "London, United Kingdom")
        self.assertTrue(JF.company_on_sponsor_allowlist("Wise"))
        self.assertFalse(JF.hide_open_non_india(row))

    def test_drop_unknown_company_without_sponsorship_text(self):
        row = job("Example Labs", "Sydney, Australia")
        self.assertTrue(JF.hide_open_non_india(row))
        visible, reason = JF.visibility(row, require_top=False)
        self.assertFalse(visible)
        self.assertIn("outside India", reason)

    def test_drop_explicit_no_sponsorship_for_unknown_company(self):
        row = job(
            "Example Labs",
            "Dubai, United Arab Emirates",
            description="Visa sponsorship is available. No visa sponsorship. Must already have the right to work.",
        )
        self.assertTrue(JF.posting_denies_sponsorship(JF.posting_text(row)))
        self.assertTrue(JF.hide_open_non_india(row))

    def test_allowlisted_company_stays_when_posting_refuses_sponsorship(self):
        row = job("Revolut", "London", description="We do not offer visa sponsorship.")
        self.assertFalse(JF.hide_open_non_india(row))

    def test_india_jobs_are_unaffected(self):
        row = job("Example Labs", "Bengaluru, India")
        self.assertFalse(JF.is_outside_india_target(row["location"]))
        self.assertFalse(JF.hide_open_non_india(row))
        self.assertTrue(JF.visibility(row, require_top=False)[0])
        mixed = job("Example Labs", "London / Bengaluru")
        self.assertFalse(JF.hide_open_non_india(mixed))

    def test_applied_and_requested_referrals_stay(self):
        applied = job("Example Labs", "Melbourne, Australia", status="Applied")
        requested = job("Example Labs", "Bangkok, Thailand", referral="requested")
        self.assertFalse(JF.hide_open_non_india(applied))
        self.assertFalse(JF.hide_open_non_india(requested))
        self.assertTrue(JF.visibility(applied)[0])
        self.assertTrue(JF.visibility(requested)[0])

    def test_needed_unknown_company_is_hidden(self):
        row = job("Example Labs", "London, England", referral="needed")
        self.assertTrue(JF.hide_open_non_india(row))
        self.assertFalse(JF.visibility(row, require_top=False)[0])


if __name__ == "__main__":
    unittest.main()

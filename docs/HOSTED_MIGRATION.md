# Hosted migration

The dashboard stays at `https://chandanmalla.github.io/job-search-dashboard/`. This branch prepares GitHub Actions so a later cutover can run without the Windows PC. It does not merge, deploy, enable a schedule, crawl, or send messages. The PC pipeline remains the only production writer.

## Public / private boundary

This repository is public. GitHub Actions logs for a public repository are public too.

Already public, and left as they are in this branch: `index.html`, `data/jobs.json`, and `data/applied_inbox.json`. The dashboard already shows some referral details. This branch does not rewrite those files to add or remove them.

Not public, and not in this branch:

- `tracked_jobs.json`
- `applied_updates.json`, `skipped_updates.json`, `referral_updates.json`
- backups of those files
- `direct_apply_companies.json`, `tg_offset.json`, `auto_referral_state.json`

Those names are gitignored. The publisher refuses to commit them. A future hosted build copies listing fields and referral **status** into the public site and stores an empty contact list. Names, notes, profile URLs, and phone numbers stay in the private store.

`data/applied_inbox.json` may contain only `job_id`, `action`, and `ts`. The GitHub-login issue is public. Its body is reduced to those job ids. Do not type notes into it.

## Public state repository

`chandanmalla/job-search-state` is public by the owner's decision. It is not a place for referral contacts. It stores sanitized listings, job ids, and statuses only. `scripts/sanitize_state.py` builds that snapshot from an allowlist. Contact names, profile URLs, notes, emails, phones, and credentials stay on the PC.

Do not replace the PC `tracked_jobs.json` with the public file. `overlay_private()` copies status and listing fields from the public snapshot and puts the local contact list back. An empty public contact list does not delete local contacts. The full archive on the PC is unchanged until a later cutover.

Hosted crawl and applied sync can run on the sanitized file: dedupe uses company, title, link, and id; marks are job ids; referral state is the status enum. Outreach history is not required for those two jobs. No separate private repository is required for crawl and applied sync. It remains required only if those workflows must edit the contact history, which they do not.

Leave `HOSTED_APPLIED_SYNC`, `HOSTED_CRAWL`, and `HOSTED_MARK_ISSUES` unset. The PC task stays the writer. A token is not required to read the public state repository. Do not point the hosted workflows at it until a cutover is reviewed.

## Schedule

The local routine is every two hours on **even IST hours** (00:00, 02:00, …, 22:00). IST is UTC+5:30, so a cron minute of 30 lands on minute 00 six hours later and keeps even/odd parity.

| UTC | IST |
| --- | --- |
| 18:30 | 00:00 |
| 20:30 | 02:00 |
| 22:30 | 04:00 |
| 00:30 | 06:00 |
| 02:30 | 08:00 |
| 04:30 | 10:00 |
| 06:30 | 12:00 |
| 08:30 | 14:00 |
| 10:30 | 16:00 |
| 12:30 | 18:00 |
| 14:30 | 20:00 |
| 16:30 | 22:00 |

The expression is `30 0,2,4,6,8,10,12,14,16,18,20,22 * * *`. Odd UTC hours would be odd IST hours (01:00, 03:00, …) and are not this routine. The expression is commented in `.github/workflows/crawl.yml`. It is not enabled. A schedule event would still publish only if `HOSTED_CRAWL=true`, which is unset.

## What was checked on the private bundle

The archive hash matches `33261389bfc0b6849c091d76637f3052ba113a637220fa4c5570c1bab2d3c5ab`. It was extracted outside the git work tree. The code modules import. Filter checks for senior titles, plain Data Scientist titles, the 3–7 year window, Singapore, Pune, multi-city Bengaluru/Pune, Infosys, and an unknown company match the module that was copied into `scripts/job_filters.py`.

`merge_referral_updates.py` in this repo reads `JT_DIR` and does not rewrite `tracked_jobs.json` when the replay leaves the canonical JSON unchanged. On the private copy, one run and a second run both reported `rewritten=0`, and the file bytes were unchanged. Applied and skipped membership and private referral fields stayed in that file. `auto_referral_needed.py --dry-run` reported `flagged=0` because the watermark is already at the newest id, and it did not modify the referral log.

The attached `generate_report.py` matches the copy inside the archive. The repository copy has the same ingest functions. It adds portable paths, `--no-telegram`, and redacted Telegram errors. Do not replace it with the PC copy.

Deloitte, EY, KPMG, and PwC now pass `is_big4`, `company_excluded` (not excluded), `company_non_product` (not a service firm), `company_product`, and `company_top`, including names such as Deloitte Consulting. McKinsey, Bain, and other staffing or IT-services firms stay excluded. The PC copy of the filter file was not edited.

`direct_apply_companies.json` matches `a38043dfde8ab8fbb4e6f609473dfb97a9dc60e5607dd679a0e76a2e637332d3`, 236 bytes, 15 string entries. It is in the local private bundle only. Merge sets referral status `apply_direct` for a visible, unapplied job at one of those companies when the current status is `none`. Applied jobs, hidden jobs, and any other referral status stay as they are. A second run does not rewrite the file. The list itself is not modified.

## Remaining blockers

- Telegram stays off. `tg_offset.json` is not required.
- Hosted variables stay unset. The dashboard pull request stays unmerged. The PC task stays the writer.
- `product_companies_allow.json` was not in the bundle. The referral script does not require it.

## Later cutover

Only when you want the PC to stop being the writer:

1. Point the hosted job at the sanitized public state. Do not copy that file over the PC tracker.
2. Run the empty-confirm dispatch and read the counts. It must not publish while the variables are unset.
3. Stop the PC scheduled task, then set `HOSTED_APPLIED_SYNC=true`.
4. Enable crawl only after one confirmed manual run, using the even-IST cron above. Leave Telegram and outreach off.

Rollback: unset the three `HOSTED_*` variables and turn the PC task back on. The local contact history is still the full file on the PC.

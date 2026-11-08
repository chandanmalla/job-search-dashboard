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

## Private canonical store (decision, not created)

Use a **private repository in the same GitHub account**. That is not a new account and not a paid plan. GitHub Free includes private repositories. This branch does not create it.

Suggested name: `job-search-state`. Put the JSON state there, not the public dashboard repo.

Provisioning, when you choose it:

1. Create the private repository. Do not make it public.
2. Create a fine-grained personal access token whose repository access is **only** that private repository, with Contents read and write. Do not grant it access to `job-search-dashboard`.
3. In the public repository, set secret `STATE_REPO_TOKEN` to that token and variable `STATE_REPO` to `OWNER/job-search-state`.
4. Leave `HOSTED_APPLIED_SYNC`, `HOSTED_CRAWL`, and `HOSTED_MARK_ISSUES` unset.

The workflow checks the private repository out into `state/private/`, which is gitignored. Until the secret exists, checkout does nothing and a publish attempt stops for missing files. No purchase is required. Running the workflows in the public repository keeps standard runner minutes free; the tradeoff is that logs are public, so the scripts print counts only.

A stronger later option, still without a new account, is to run the merge inside the private repository so the logs are private, and push only the clamped site files to the public repository. That uses the private repository's included Actions minutes. It is not set up here.

Do not use an orphan branch, a public gist, or this public repository for the canonical JSON.

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

`company_excluded()` still returns true for Deloitte even though `company_product()` does not. That is the shipped filter module, unchanged. Say if Big 4 visibility should follow `company_product()` instead.

## Remaining blockers

- The private repository and `STATE_REPO_TOKEN` do not exist yet. That is intentional.
- `direct_apply_companies.json` was not in the bundle. Existing `apply_direct` rows stay as they are. New direct-apply flags will not be added until that file is in the private store.
- `product_companies_allow.json` was not in the bundle. The referral script no longer needs it for the current rule.
- `tg_offset.json` was not in the bundle. The offset is inside the private tracked file. Do not enable Telegram sync.
- Hosted variables stay unset. The PC task stays the writer. Do not stop it for this branch.

## Later cutover

Only after you decide the private store is in place and you want the PC to stop being the writer:

1. Put the JSON files in the private repository. Do not commit them here.
2. Set `STATE_REPO` and `STATE_REPO_TOKEN`.
3. Run the empty-confirm dispatch and read the counts. It must not publish while the variables are unset.
4. Stop the PC scheduled task, then set `HOSTED_APPLIED_SYNC=true`.
5. Enable crawl only after one confirmed manual run, using the even-IST cron above. Leave Telegram and outreach off.

Rollback: unset the three `HOSTED_*` variables, turn the PC task back on, and redeploy the previous public commit of `index.html`. The private JSON is untouched by a failed public publish.

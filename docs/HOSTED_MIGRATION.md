# Hosted migration

The live dashboard stays at `https://chandanmalla.github.io/job-search-dashboard/`. This branch prepares a GitHub Actions pipeline that can record website marks, crawl, rebuild `index.html`, and publish Pages without the Windows PC named Nitya. It does not turn that pipeline on.

Nothing here merges to `main`, deploys, enables a schedule, buys a service, sends Telegram, runs outreach, or deletes canonical data.

## What already happened on 8 Nov 2026

Commit `115f06a` (`115f06acb8234508690b29d600ccdf79163457b6`) is the sweep that cleared the pending inbox. The parent of that commit held 49 `applied` inbox rows: 20 timestamped `2026-11-05` and 29 timestamped `2026-11-08`. After the commit:

| | Before `c0f6220` | After `115f06a` |
| --- | --- | --- |
| Embedded `DB_APPLIED` | 433 | 482 |
| Applied ids that are also rows in `data/jobs.json` (the on-screen Applied count) | 334 | 383 |
| `DB_SKIPPED` | 73 | 73 |
| Inbox | 49 marks | `[]` |

The 49 new embedded ids are exactly those inbox ids. No skipped id was removed. The same commit also added 13 job rows (`J646`–`J658`). Referral counts on the dashboard data went from 73 `needed` / 11 `apply_direct` to 85 `needed` / 12 `apply_direct` because of those new rows, not because an existing row changed status. That crawl, referral flagging, and the Telegram digest were side effects of running the whole PC orchestrator for a status sync. Hosted applied-sync does not call the crawler, `auto_referral_needed.py`, Telegram, or `outreach_queue.py`.

`HEAD` is still 482 applied and 73 skipped. `data/applied_inbox.json` on `main` still has the later marks `J646` and `J649`. This branch does not process them.

## Why GitHub Actions is enough

The work is a batch: read a JSON inbox, update JSON state, rebuild two static files, push, and let the existing Pages workflow serve them. A VM, worker, or database would add an account and a second writer. Actions already has a short-lived `GITHUB_TOKEN` and can deploy Pages.

| | GitHub Actions on this public repo | Private repo or a small VM |
| --- | --- | --- |
| Runner cost | $0 for standard GitHub-hosted runners. Do not select a larger runner; those are billed even on public repos. | Linux 2-core is $0.006/minute after the plan's included compute (GitHub Free documents about $12/month, and the pricing page still lists 2,000 minutes). Twelve 15-minute crawls a day is about 5,400 minutes/month. |
| Pages | Free. Published site cap 1 GB. Soft bandwidth cap 100 GB/month. Deploy timeout 10 minutes. The custom workflow is not under the 10 Jekyll builds/hour soft limit. | Private Pages is not on every free plan. |
| Always-on bot | Not required for marks or crawl. A 24/7 Telegram listener is a separate process and stays off. | A VM would be the thing that has to stay up. |
| Schedule accuracy | GitHub cron is best-effort and can start late. Every two hours is within what it is for. | A VM cron is sharper and is another writer to disable. |

Checked against GitHub's Actions billing and Pages limits docs while preparing this branch. Re-check those pages before enabling anything if billing copy has moved.

The repo is public. `state/job-tracker/` will be public git data once the bundle is committed. The Pages artifact is only `index.html`, `data/jobs.json`, and `data/applied_inbox.json`, so the canonical file is not copied onto the website. `data/jobs.json` already publishes referral notes. Read `tracked_jobs.json` for contact details before its first commit and remove anything that is not already on the dashboard.

## Two pipelines

`scripts/hosted_runner.py --mode applied-sync`

1. Snapshot canonical JSON under `state/job-tracker/backups/` (five stamps kept; git history is the real backup).
2. `process_inbox.py` appends marks into `*_updates.json` and removes only the fingerprints it accepted. A retry does not duplicate ids. Unrecognized inbox entries stay. A JSON parse error leaves the inbox as it was.
3. `merge_referral_updates.py` from the bundle.
4. `build_site.py`, then the publish guard. Applied and skipped ids must be a superset of the previous dashboard. Existing referral statuses `apply_direct`, `referred`, `requested`, and `skipped` cannot change. Applied-sync also refuses new or deleted job rows.
5. One commit of an explicit path list, then Pages. A failed step commits nothing. Push rejection checks out `origin/main` and replays the idempotent steps, up to three times.

The command list is `process_inbox.py`, `merge_referral_updates.py`, `build_site.py`. Passing notification flags to applied-sync is a failure, not a send.

`scripts/hosted_runner.py --mode crawl`

Runs the sweep, then `auto_referral_needed.py`, merge, optional report ingest, referral flag, merge, and build. `generate_report.py` is called with `--no-telegram` unless `--notifications` is passed. Outreach runs only with `--outreach`. The crawl workflows do not pass those flags. New best-fit rows may move from referral `none` to `needed`. They may not move to `requested`. `apply_direct` stays `apply_direct`.

Crawl HTTP GETs retry 429, 502, and 503 at most four times. Each wait is capped at 20 seconds. Tests stub the socket; they do not scrape.

`scripts/cron_runner.py` remains the PC orchestrator. It still syncs Telegram, crawls, flags referrals, sends the digest, and refreshes outreach, using `JT_DIR` / the historical Windows path. It no longer prints success when a step failed, no longer runs `git add .`, and no longer rebases with `-X ours` (that could drop inbox marks). Disable that scheduled task before the hosted variables are set. Do not also restore its two-hour routine at 9 Nov 00:00 IST.

## Marks without a long-lived browser token

A static Pages site cannot mint a short-lived GitHub token by itself. A backend that exchanged OAuth codes would be a new service. Two authenticated writes are supported, and neither is a public anonymous write:

1. **GitHub login (preferred).** "Sync with GitHub login" opens a prefilled issue. The workflow `.github/workflows/mark-via-issue.yml` accepts it only from `MARK_AUTHORS` (default `chandanmalla`), rejects token-shaped text without storing it, and appends to the inbox only when the repository variable `HOSTED_MARK_ISSUES` is `true`. Until then the open issue is the record.
2. **Optional fine-grained PAT.** "Connect GitHub" still stores a token in `localStorage` only. Use one repo, Contents read/write, and a short expiry. It is not committed. Prefer the issue path and remove the token from the browser when you can.

Processing and publishing use the per-job `GITHUB_TOKEN`. That token's pushes do not start another workflow run, so the same job deploys Pages.

## Canonical bundle to copy

Put these files in `state/job-tracker/`. Do not send `config.json`, `.env`, browser tokens, `python-embed/`, `git-portable/`, logs, or Excel reports.

Required before applied-sync can publish:

- `tracked_jobs.json`
- `job_filters.py`
- `merge_referral_updates.py`
- `applied_updates.json`
- `skipped_updates.json`
- `referral_updates.json`

Also required before crawl can publish:

- `auto_referral_needed.py`
- `cron_state.json`

Copy any local module that those three Python files import. Preflight parses them and names a missing local import; it does not execute them. Known pip packages (`openpyxl`, `xlsxwriter`, `python-jobspy`) are not local files. `python-jobspy` is not installed by the workflow. Add it only when you intentionally enable crawl.

Diff `job-tracker/generate_report.py` against `scripts/generate_report.py`. The repo copy is the one the hosted crawl runs, and it now has `--no-telegram` plus portable paths. If the PC copy has newer filter or ingest behavior, bring that behavior across without dropping `--no-telegram`.

Not required for the default migration:

- `tg_offset.json`, and only if Telegram command sync is later enabled. Missing offset refuses to start at 0, because that would replay old commands and send acknowledgements.
- `outreach_queue.py`, only if outreach is later enabled.
- `feed_health.json`, optional continuity for the crawl health log.
- User profile. The dashboard already has its display name and email. `DASHBOARD_USER_NAME`, `DASHBOARD_USER_EMAIL`, and `DASHBOARD_USER_PHONE` override them without a config file.

Filter rules stay in the copied `job_filters.py`. This branch does not re-code experience, title, or company policy. The sweep file still contains the location and Grab checks that were already in the repo (India except Pune, Chennai, West Bengal, Kolkata, and Tamil Nadu; UK; Australia; Thailand; Dubai/UAE; no Singapore; Grab only Bangkok and India).

## Secrets and variables

Create no secrets for the default cutover.

| Name | Kind | Default | Effect |
| --- | --- | --- | --- |
| `HOSTED_APPLIED_SYNC` | repository variable | unset | `true` lets inbox pushes and a confirmed dispatch merge and publish. |
| `HOSTED_CRAWL` | repository variable | unset | `true` plus dispatch confirm `pc-cron-stopped` runs a crawl. There is no schedule in the workflow. |
| `HOSTED_MARK_ISSUES` | repository variable | unset | `true` lets an allow-listed issue append to the inbox. |
| `MARK_AUTHORS` | repository variable | `chandanmalla` | Comma-separated GitHub logins. |
| `TELEGRAM_BOT_TOKEN` | secret | absent | Used only by an explicit notification or Telegram-sync run. |
| `TELEGRAM_CHAT_IDS` | secret | absent | Comma-separated chat ids. Same gate. |

`workflow_dispatch` without the confirm string, or without the matching variable, is preflight only. Preflight exits non-zero when the bundle is missing and does not edit the dashboard. That red run means "not ready", not "the site was changed".

## Safe activation

The PC task has been daily at 08:00 IST through 8 Nov. Do not start a two-hour PC routine at 9 Nov 00:00 IST and also enable Actions. One writer.

1. Copy the bundle onto this branch and push. Run the unit tests. Run **Applied sync** and **Crawl** via workflow dispatch with an empty confirm box. Both should report the file list and must not change `main` if the variables are unset.
2. On the PC, disable the scheduled task that runs `cron_runner.py`. Confirm it is not going to fire at 08:00 IST or at midnight.
3. Set `HOSTED_APPLIED_SYNC` to `true`.
4. Run **Applied sync** once with confirm `pc-cron-stopped`. Check `state/health.json` is `"ok": true`, the skipped ids are still 73 or a superset, and no Telegram message arrived.
5. Set `HOSTED_MARK_ISSUES` to `true` if you want the login button to write. Leave the browser token unused.
6. Crawl stays manual. After one confirmed crawl looks right, the schedule to add to `.github/workflows/crawl.yml` is:

```yaml
on:
  schedule:
    - cron: "30 0,2,4,6,8,10,12,14,16,18,20,22 * * *"
  workflow_dispatch:
```

That is 00:00 IST and every two hours after (18:30 UTC is 00:00 IST). The run script already treats a `schedule` event as a crawl only when `HOSTED_CRAWL` is `true`; unset, the run stays a preflight. Turn the variable on only when the PC task is off. Do not combine that change with Telegram.

Health JSON records skipped Telegram, outreach, and, for applied-sync, skipped crawl. A failed merge or a guard failure restores the previous `index.html` and `data/jobs.json` in the worktree and does not push.

## Rollback

1. Delete or set `HOSTED_APPLIED_SYNC`, `HOSTED_CRAWL`, and `HOSTED_MARK_ISSUES` to anything other than `true`.
2. Re-enable the PC task if that machine should be the writer again. `cron_runner.py` still understands the Windows paths.
3. `git revert` the bad publish, or restore `state/job-tracker/*.json` from `state/job-tracker/backups/<stamp>/` or from the previous commit. Push. Pages serves that commit's `index.html`.
4. Inbox rows are in git history. A publish that fails never clears them on `main`.

## Tests

`python3 -m unittest discover -s tests -v`

Covers the 49-mark commit (including 334 and 383 visible applied, 433 and 482 embedded, 73 skips), duplicate retry, concurrent inbox writers, referral and skip files left untouched, publish-guard rollback, bounded HTTP backoff, crawl refusal before any HTTP call when `job_filters.py` is absent, secret-path refusal, and a local git push retry. No test scrapes a career site.

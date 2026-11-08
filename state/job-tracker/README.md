# Canonical job-tracker state

This directory is the hosted copy of the PC folder
`C:\Users\chand\Downloads\Job Search\job-tracker`.

It is empty on purpose. Do not invent `tracked_jobs.json`, `job_filters.py`, or the
update logs. Copy the secret-free bundle listed in `docs/HOSTED_MIGRATION.md`.

Do not put `config.json`, `.env`, tokens, or Telegram credentials here.
`config.json` is gitignored everywhere in this repo. Put Telegram values in
GitHub Actions secrets only when notifications are deliberately enabled.

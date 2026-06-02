# RemoteJobFinder MVP

This project is a starter MVP for the daily AI remote job hunter workflow described in the planning notes.

## What is included

- Fetches jobs from public job APIs (Himalayas, Remotive, Lever)
- Normalizes everything into one shared job format
- Filters for remote/customer-facing roles
- Removes duplicate jobs using a fingerprint hash
- Scores the top matches with a simple heuristic
- Exposes a runnable CLI entry point for the daily job flow

## Run locally

1. npm install
2. npm run dev

## Next steps

- Add Supabase persistence for `jobs_seen`, `daily_reports`, and `errors`
- Connect Google Drive resume uploads
- Add Gmail delivery and a GitHub Actions cron
- Replace the heuristic scorer with an AI-based scorer

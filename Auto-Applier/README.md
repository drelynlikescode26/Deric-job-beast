# Auto-Applier

This repository contains a local autonomous job application system with Telegram control, scouting, and form execution.

## Quick Start

1. Copy `.env.example` to `.env` and fill in your secrets.
2. Install dependencies:

```bash
cd /Users/deric/Deric-job-beast/Auto-Applier
pip install -r requirements.txt
playwright install
```

3. Optionally set `BROWSER_PROFILE_PATH` in `.env` for persistent sessions.
4. Run the orchestrator and optionally scout on startup:

```bash
python main.py --scout-now
```

5. Send job URLs to your Telegram bot or reply `RUN` to execute the queue.

## Files

- `main.py`: starts the Telegram bridge and optional scouter.
- `telegram_bot.py`: listens for URLs and triggers the executor.
- `scouter.py`: finds new jobs and adds them to `queue.json`.
- `executor.py`: applies to queued jobs, uploads resumes, and saves success state.
- `browser_tester.py`: tests a single job URL with resume upload.
- `profile.json`: your profile data and target URLs.
- `queue.json`: queued jobs waiting for execution.
- `state_tracker.json`: applied job URLs.
- `accounts.json`: generated account credentials.

## Notes

- This is a foundation for job automation. Some corporate sites require further site-specific selector tuning.
- Use `playwright install` before running browser automation.

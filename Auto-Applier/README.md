# Auto-Applier

This repository contains a local autonomous job application system with Telegram control, scouting, and form execution.

## Quick Start

1. Copy `.env.example` to `.env` and fill in your secrets.
2. Create and activate a local Python virtual environment, then install dependencies:

```bash
cd /Users/deric/Deric-job-beast/Auto-Applier
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
playwright install
```

3. To avoid Google's automated-browser block, set this in `.env`:

```bash
CHROME_CDP_URL=http://localhost:9222
```

Then quit Chrome and launch it manually with debugging enabled:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222
```

Leave that Chrome window open, log in to Google and LinkedIn there, then run the bot from a second terminal. When `CHROME_CDP_URL` is set, the scouter and executor attach to this existing browser instead of launching a new scripted Chrome.

4. If you prefer the project-local profile workflow instead of remote debugging, use the built-in warm-up command:

```bash
./run.sh warmup
```

Then log into LinkedIn, Google, Indeed, or any other site in that Chrome window and close it when done. The local profile is stored in `chrome_profile` by default.

5. Optionally set `BROWSER_PROFILE_PATH` and `CHROME_PATH` in `.env` for the fallback mode used when `CHROME_CDP_URL` is not set.

6. Make sure `OPENAI_API_KEY` is set in `.env`; this enables Workday/Taleo prompt routing via `browser-use` and `langchain-openai`.

6. Run the orchestrator and optionally scout on startup:

   - In VS Code: open Command Palette (`Cmd+Shift+P`), choose `Tasks: Run Task`, then select `Auto-Applier: Run Scouter`.
   - To start the Telegram bot from VS Code: use `Tasks: Run Task` → `Auto-Applier: Start Telegram Bot`.

7. Alternatively, run from the terminal:

```bash
python main.py --scout-now
```

8. If you want a simpler launcher, use the built-in script:

```bash
./run.sh scout
./run.sh telegram
./run.sh executor
```

9. You can also run the app from VS Code directly using Tasks or Launch configurations:

- `Cmd+Shift+P` → `Tasks: Run Task` → `Auto-Applier: Run Scouter`
- `Cmd+Shift+P` → `Tasks: Run Task` → `Auto-Applier: Start Telegram Bot`
- Use the Debug panel to launch `Python: Run Auto-Applier`, `Python: Start Telegram Bot`, or `Python: Run Executor`

10. Send job URLs to your Telegram bot or reply `RUN` to execute the queue.

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

#!/usr/bin/env python3
"""Main orchestrator: starts Telegram bot and schedules the scouter at 8 AM local time."""
import argparse
import threading
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger


def run_bot():
    try:
        from telegram_bot import main as bot_main
        bot_main()
    except Exception as exc:
        print(f"Telegram bot failed to start: {exc}")


def run_scout_once():
    from scouter import scout_once

    scout_once()


def schedule_daily_scout():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_scout_once,
        CronTrigger(hour=8, minute=0, timezone="local"),
        id="daily_scout",
        replace_existing=True,
    )
    scheduler.start()
    print("Scheduled daily scouter at 08:00 local time.")
    return scheduler


def main():
    parser = argparse.ArgumentParser(description="Auto-Applier orchestrator")
    parser.add_argument("--scout-now", action="store_true", help="Run the scouter once at startup")
    args = parser.parse_args()

    if args.scout_now:
        print("Running scouter now...")
        run_scout_once()
        return

    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    time.sleep(1)
    print("Telegram bot started in the background.")

    schedule_daily_scout()

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("Shutting down")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Run this locally to verify your Telegram bot is connected and can reach you.

Usage:
    cd Auto-Applier
    python test_telegram.py
"""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


async def run():
    issues = []
    if not TOKEN:
        issues.append("TELEGRAM_TOKEN is not set in .env")
    if not CHAT_ID:
        issues.append("TELEGRAM_CHAT_ID is not set in .env")
    if issues:
        for i in issues:
            print(f"  MISSING: {i}")
        return

    try:
        from telegram import Bot
    except ImportError:
        print("  ERROR: python-telegram-bot not installed. Run: pip install python-telegram-bot")
        return

    print(f"  Connecting to Telegram with token ending ...{TOKEN[-6:]}")
    try:
        bot = Bot(TOKEN)
        me = await bot.get_me()
        print(f"  OK  Bot identity: @{me.username} ({me.first_name})")
    except Exception as e:
        print(f"  FAIL  Could not connect — check TELEGRAM_TOKEN: {e}")
        return

    print(f"  Sending test message to chat_id={CHAT_ID} ...")
    try:
        msg = await bot.send_message(
            chat_id=int(CHAT_ID),
            text=(
                "Auto-Applier test message\n"
                "Bot is connected and ready.\n"
                "Send HELP to see available commands."
            ),
        )
        print(f"  OK  Message delivered (id={msg.message_id})")
        print()
        print("  All good — check your Telegram to confirm the message arrived.")
    except Exception as e:
        print(f"  FAIL  Could not send message — check TELEGRAM_CHAT_ID: {e}")


if __name__ == "__main__":
    print()
    print("Telegram connectivity test")
    print("-" * 34)
    asyncio.run(run())
    print()

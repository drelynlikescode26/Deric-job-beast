#!/usr/bin/env python3
"""Telegram bridge: listens for messages, appends URLs to queue, and triggers executor on RUN."""
import os
import threading
import json
from dotenv import load_dotenv
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
QUEUE_PATH = os.path.join(os.path.dirname(__file__), "queue.json")

bot = Bot(TOKEN) if TOKEN else None


def append_to_queue(url: str):
    try:
        with open(QUEUE_PATH, "r+") as f:
            q = json.load(f)
            q.append({"source": "telegram", "url": url})
            f.seek(0)
            json.dump(q, f, indent=2)
            f.truncate()
        return True, None
    except Exception as e:
        return False, str(e)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.upper() == "RUN":
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Triggering executor...")

        def runner():
            from executor import run_executor
            run_executor()

        t = threading.Thread(target=runner, daemon=True)
        t.start()
        return

    if text.startswith("http://") or text.startswith("https://"):
        ok, err = append_to_queue(text)
        if ok:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="URL added to queue.json")
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Failed to add URL: {err}")
        return

    await context.bot.send_message(chat_id=update.effective_chat.id, text="Send a job URL to add to queue, or reply 'RUN' to execute the queue.")


def send_message(text: str):
    if bot and CHAT_ID:
        bot.send_message(chat_id=int(CHAT_ID), text=text)


def send_photo(path: str, caption: str | None = None):
    if bot and CHAT_ID:
        with open(path, "rb") as f:
            bot.send_photo(chat_id=int(CHAT_ID), photo=f, caption=caption)


def main():
    if not TOKEN or not CHAT_ID:
        print("Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in environment or .env")
        return

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    try:
        send_message("Auto-Applier Telegram bridge started.")
    except Exception:
        pass
    app.run_polling()


if __name__ == '__main__':
    main()

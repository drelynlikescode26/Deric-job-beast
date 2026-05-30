#!/usr/bin/env python3
"""Telegram bridge: listens for messages, appends URLs to queue, and triggers executor on RUN."""
import os
import threading
import json
import asyncio
from dotenv import load_dotenv
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

_DIR = os.path.dirname(__file__)
QUEUE_PATH = os.path.join(_DIR, "queue.json")
STATE_PATH = os.path.join(_DIR, "state_tracker.json")

bot = None

HELP_TEXT = (
    "Commands:\n"
    "  RUN       — apply to all queued jobs\n"
    "  SCOUT     — run the scouter now to find new jobs\n"
    "  STATUS    — queue size, total applied, last application\n"
    "  QUEUE     — list jobs currently in the queue\n"
    "  CLEAR     — empty the queue\n"
    "  HISTORY [N] — last N applied jobs (default 5)\n"
    "  <URL>     — add a job URL directly to the queue"
)


def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, value):
    with open(path, "w") as f:
        json.dump(value, f, indent=2)


def get_bot():
    global bot
    if bot is None and TOKEN:
        try:
            bot = Bot(TOKEN)
        except Exception:
            bot = None
    return bot


def append_to_queue(url: str):
    try:
        if not os.path.exists(QUEUE_PATH):
            write_json(QUEUE_PATH, [])
        q = read_json(QUEUE_PATH, [])
        if not isinstance(q, list):
            q = []
        # Deduplicate
        existing_urls = {item["url"] if isinstance(item, dict) else item for item in q}
        if url in existing_urls:
            return True, "already queued"
        q.append({"source": "telegram", "url": url})
        write_json(QUEUE_PATH, q)
        return True, None
    except Exception as e:
        return False, str(e)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    cmd = text.upper().split()[0]

    # ── RUN ──────────────────────────────────────────────────────────
    if cmd == "RUN":
        queue = read_json(QUEUE_PATH, [])
        if not queue:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Queue is empty. Send job URLs or run SCOUT first.")
            return
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Triggering executor on {len(queue)} job(s)...")

        def runner():
            from executor import run_executor
            run_executor()

        threading.Thread(target=runner, daemon=True).start()
        return

    # ── SCOUT ─────────────────────────────────────────────────────────
    if cmd == "SCOUT":
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Starting scouter — this may take a few minutes...")

        def do_scout():
            from scouter import scout_once
            scout_once()

        threading.Thread(target=do_scout, daemon=True).start()
        return

    # ── STATUS ────────────────────────────────────────────────────────
    if cmd == "STATUS":
        queue = read_json(QUEUE_PATH, [])
        state_raw = read_json(STATE_PATH, [])
        queue_count = len(queue)
        applied_count = len(state_raw)

        last_line = ""
        for item in reversed(state_raw):
            if isinstance(item, dict) and item.get("applied_at"):
                last_line = f"\nLast applied: {item.get('company', '?')} on {item['applied_at']}"
                break

        msg = (
            f"Queue:   {queue_count} job(s) waiting\n"
            f"Applied: {applied_count} total{last_line}"
        )
        await context.bot.send_message(chat_id=update.effective_chat.id, text=msg)
        return

    # ── QUEUE ─────────────────────────────────────────────────────────
    if cmd == "QUEUE":
        queue = read_json(QUEUE_PATH, [])
        if not queue:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Queue is empty.")
            return
        lines = [f"Queue ({len(queue)} job(s)):"]
        for i, item in enumerate(queue, 1):
            url = item["url"] if isinstance(item, dict) else item
            typ = item.get("type", "?") if isinstance(item, dict) else "?"
            score = item.get("score")
            score_str = f" score={score}" if score is not None else ""
            short_url = url[:70] + ("…" if len(url) > 70 else "")
            lines.append(f"{i}. [{typ}{score_str}] {short_url}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="\n".join(lines))
        return

    # ── CLEAR ─────────────────────────────────────────────────────────
    if cmd == "CLEAR":
        queue = read_json(QUEUE_PATH, [])
        count = len(queue)
        write_json(QUEUE_PATH, [])
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Cleared {count} job(s) from the queue.")
        return

    # ── HISTORY ───────────────────────────────────────────────────────
    if cmd == "HISTORY":
        parts = text.split()
        n = 5
        if len(parts) > 1:
            try:
                n = int(parts[1])
            except ValueError:
                pass
        state_raw = read_json(STATE_PATH, [])
        if not state_raw:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="No applications recorded yet.")
            return
        recent = list(reversed(state_raw[-n:]))
        lines = [f"Last {min(n, len(recent))} application(s):"]
        for item in recent:
            if isinstance(item, dict):
                company = item.get("company", "?")
                status = item.get("status", "?")
                applied_at = item.get("applied_at", "?")
                typ = item.get("type", "?")
                lines.append(f"• {company} [{typ}] {status} — {applied_at}")
            else:
                lines.append(f"• {item}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="\n".join(lines))
        return

    # ── URL ───────────────────────────────────────────────────────────
    if text.startswith("http://") or text.startswith("https://"):
        ok, err = append_to_queue(text)
        if ok:
            msg = "Already in queue." if err == "already queued" else "URL added to queue."
            await context.bot.send_message(chat_id=update.effective_chat.id, text=msg)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Failed to add URL: {err}")
        return

    # ── FALLBACK ──────────────────────────────────────────────────────
    await context.bot.send_message(chat_id=update.effective_chat.id, text=HELP_TEXT)


def _async_send_message(text: str):
    b = get_bot()
    if b and CHAT_ID:
        return b.send_message(chat_id=int(CHAT_ID), text=text)
    return None


def _async_send_photo(path: str, caption: str | None = None):
    async def _send():
        b = get_bot()
        if b and CHAT_ID:
            with open(path, "rb") as f:
                return await b.send_photo(chat_id=int(CHAT_ID), photo=f, caption=caption)
    return _send()


def send_message(text: str):
    try:
        coro = _async_send_message(text)
        if coro:
            try:
                loop = asyncio.get_running_loop()
                asyncio.ensure_future(coro)
            except RuntimeError:
                asyncio.run(coro)
    except Exception:
        pass


def send_photo(path: str, caption: str | None = None):
    try:
        if not os.path.exists(path):
            return
        coro = _async_send_photo(path, caption)
        try:
            loop = asyncio.get_running_loop()
            asyncio.ensure_future(coro)
        except RuntimeError:
            asyncio.run(coro)
    except Exception:
        pass


def main():
    if not TOKEN or not CHAT_ID:
        print("Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in environment or .env")
        return

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    try:
        send_message("Auto-Applier online. Send HELP for commands.")
    except Exception:
        pass
    app.run_polling()


if __name__ == '__main__':
    main()

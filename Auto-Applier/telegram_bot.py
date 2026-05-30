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
ACCOUNTS_PATH = os.path.join(_DIR, "accounts.json")

bot = None

HELP_TEXT = (
    "Commands:\n"
    "  RUN         — apply to all queued jobs\n"
    "  SCOUT       — run the scouter now to find new jobs\n"
    "  STATUS      — queue size, applied count, pending assessments\n"
    "  QUEUE       — list jobs currently in the queue\n"
    "  CLEAR       — empty the queue\n"
    "  HISTORY [N] — last N job outcomes (default 5)\n"
    "  PENDING     — jobs flagged for manual assessment\n"
    "  ACCOUNTS    — sites where accounts were created\n"
    "  <URL>       — add a job URL directly to the queue"
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
        applied = [i for i in state_raw if isinstance(i, dict) and i.get("status") == "applied"]
        pending = [i for i in state_raw if isinstance(i, dict) and i.get("status") == "assessment_required"]

        last_line = ""
        for item in reversed(applied):
            ts = item.get("recorded_at") or item.get("applied_at", "?")
            last_line = f"\nLast applied: {item.get('company', '?')} on {ts}"
            break

        pending_line = f"\nAssessments pending: {len(pending)} (send PENDING to review)" if pending else ""

        msg = (
            f"Queue:    {queue_count} job(s) waiting\n"
            f"Applied:  {len(applied)} total{last_line}{pending_line}"
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
        lines = [f"Last {min(n, len(recent))} outcome(s):"]
        STATUS_EMOJI = {"applied": "✓", "assessment_required": "⚠", "skipped": "–"}
        for item in recent:
            if isinstance(item, dict):
                company = item.get("company", "?")
                status = item.get("status", "?")
                ts = item.get("recorded_at") or item.get("applied_at", "?")
                typ = item.get("type", "?")
                icon = STATUS_EMOJI.get(status, "?")
                lines.append(f"{icon} {company} [{typ}] {status} — {ts}")
            else:
                lines.append(f"  {item}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="\n".join(lines))
        return

    # ── PENDING ───────────────────────────────────────────────────────
    if cmd == "PENDING":
        state_raw = read_json(STATE_PATH, [])
        pending = [i for i in state_raw if isinstance(i, dict) and i.get("status") == "assessment_required"]
        if not pending:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="No assessments pending — you're all clear.")
            return
        lines = [f"Assessments to complete manually ({len(pending)}):"]
        for item in pending:
            company = item.get("company", "?")
            notes = item.get("notes", "")
            ts = item.get("recorded_at", "?")
            url = item.get("url", "")
            short_url = url[:70] + ("…" if len(url) > 70 else "")
            lines.append(f"• {company} — {notes} ({ts})\n  {short_url}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="\n".join(lines))
        return

    # ── ACCOUNTS ──────────────────────────────────────────────────────
    if cmd == "ACCOUNTS":
        accounts = read_json(ACCOUNTS_PATH, {})
        if not accounts:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="No accounts created yet.")
            return
        lines = [f"Accounts on file ({len(accounts)} site(s)):"]
        for domain, entries in accounts.items():
            count = len(entries)
            latest_ts = entries[-1].get("created_at", "?") if entries else "?"
            lines.append(f"• {domain} — {count} account(s), last created {latest_ts}")
        lines.append("\nCredentials are in accounts.json on your local machine.")
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

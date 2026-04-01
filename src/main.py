import os
import re
import datetime
import maxy_home  # loads .env from MAXY_HOME
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler,
    CommandHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from brain import think, get_backend, BACKEND_GEMINI, BACKEND_OLLAMA
from memory import save_message, save_note, save_task, list_tasks, complete_task, delete_task, set_config, get_config
from reminders import add_reminder, parse_duration, get_due_reminders, mark_sent, list_upcoming


pending_emails = {}

# ── Email helpers ─────────────────────────────────────────────────────────────

def parse_draft(text: str):
    to, subject, body = "", "", ""
    to_match   = re.search(r'TO:\s*(.+)',         text, re.IGNORECASE)
    sub_match  = re.search(r'SUBJECT:\s*(.+)',    text, re.IGNORECASE)
    body_match = re.search(r'BODY:\s*\n([\s\S]+)', text, re.IGNORECASE)
    if to_match:   to      = to_match.group(1).strip()
    if sub_match:  subject = sub_match.group(1).strip()
    if body_match: body    = body_match.group(1).strip()
    return to, subject, body

# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hey, I'm Maxy — your personal AI. I'm live and ready.\n\n"
        "Commands:\n"
        "/brief — morning summary\n"
        "/inbox — check unread emails\n"
        "/weather [city] — current weather\n"
        "/search <query> — web search\n"
        "/remind <duration> <message> — set a reminder\n"
        "/reminders — list upcoming reminders\n"
        "/todo add|list|done|delete — manage tasks\n"
        "/note <text> — save a note\n"
        "/model — show or switch AI model (Gemini / Ollama)\n\n"
        "Or just talk to me naturally."
    )

# ── General message ───────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id   = str(update.effective_user.id)
    user_text = update.message.text

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    save_message(user_id, "user", user_text)
    reply = think(user_id, user_text)
    save_message(user_id, "assistant", reply)

    is_draft = (
        "TO:" in reply.upper() and
        "SUBJECT:" in reply.upper() and
        "BODY:" in reply.upper()
    )

    if is_draft:
        to, subject, body = parse_draft(reply)
        if to and body:
            pending_emails[user_id] = {"to": to, "subject": subject, "body": body}
            preview = (
                f"Draft ready:\n\nTo: {to}\nSubject: {subject}\n\n{body}\n\nSend this email?"
            )
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("Send",   callback_data=f"send_{user_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"cancel_{user_id}")
            ]])
            await update.message.reply_text(preview, reply_markup=keyboard)
            return

    await update.message.reply_text(reply)

# ── /weather ──────────────────────────────────────────────────────────────────

async def handle_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    city = " ".join(context.args).strip() if context.args else "Chennai"
    from weather import get_weather
    result = get_weather(city)
    await update.message.reply_text(result)

# ── /search ───────────────────────────────────────────────────────────────────

async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /search <query>")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    query = " ".join(context.args)
    from search import web_search
    results = web_search(query)
    await update.message.reply_text(results)

# ── /remind ───────────────────────────────────────────────────────────────────

async def handle_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /remind <duration> <message>\n"
            "Examples:\n  /remind 30m take a break\n  /remind 2h call Priya\n  /remind 1d follow up on invoice"
        )
        return

    duration_str = context.args[0]
    message      = " ".join(context.args[1:])
    delta        = parse_duration(duration_str)

    if delta is None:
        await update.message.reply_text(
            f"Couldn't parse '{duration_str}'. Use formats like 30m, 2h, 1d."
        )
        return

    fire_at = datetime.datetime.now() + delta
    user_id = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)

    add_reminder(user_id, chat_id, message, fire_at)

    fire_str = fire_at.strftime("%I:%M %p")
    if delta >= datetime.timedelta(days=1):
        fire_str = fire_at.strftime("%b %d at %I:%M %p")

    await update.message.reply_text(f"Reminder set for {fire_str}: {message}")

# ── /reminders ────────────────────────────────────────────────────────────────

async def handle_list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    rows    = list_upcoming(user_id)
    if not rows:
        await update.message.reply_text("No upcoming reminders.")
        return
    lines = []
    for rid, msg, fire_at in rows:
        dt = datetime.datetime.fromisoformat(fire_at)
        lines.append(f"• [{rid}] {dt.strftime('%b %d %I:%M %p')} — {msg}")
    await update.message.reply_text("Upcoming reminders:\n" + "\n".join(lines))

# ── /todo ─────────────────────────────────────────────────────────────────────

async def handle_todo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "  /todo add <task>\n"
            "  /todo list\n"
            "  /todo done <id>\n"
            "  /todo delete <id>"
        )
        return

    sub = context.args[0].lower()

    if sub == "add":
        task = " ".join(context.args[1:]).strip()
        if not task:
            await update.message.reply_text("What's the task? /todo add <task>")
            return
        save_task(user_id, task)
        await update.message.reply_text(f"Added: {task}")

    elif sub == "list":
        tasks = list_tasks(user_id)
        if not tasks:
            await update.message.reply_text("No tasks yet. Add one with /todo add <task>")
            return
        lines = []
        for tid, task, done in tasks:
            status = "✓" if done else "○"
            lines.append(f"{status} [{tid}] {task}")
        await update.message.reply_text("Your tasks:\n" + "\n".join(lines))

    elif sub == "done":
        if len(context.args) < 2 or not context.args[1].isdigit():
            await update.message.reply_text("Usage: /todo done <id>")
            return
        task_id = int(context.args[1])
        if complete_task(user_id, task_id):
            await update.message.reply_text(f"Task {task_id} marked done.")
        else:
            await update.message.reply_text(f"No task found with id {task_id}.")

    elif sub == "delete":
        if len(context.args) < 2 or not context.args[1].isdigit():
            await update.message.reply_text("Usage: /todo delete <id>")
            return
        task_id = int(context.args[1])
        if delete_task(user_id, task_id):
            await update.message.reply_text(f"Task {task_id} deleted.")
        else:
            await update.message.reply_text(f"No task found with id {task_id}.")

    else:
        await update.message.reply_text(
            "Unknown subcommand. Use: add, list, done, delete"
        )

# ── /brief ────────────────────────────────────────────────────────────────────

async def handle_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /model              — show current model
    /model list         — list available Ollama models
    /model gemini       — switch to Gemini
    /model llama3.1:8b  — switch to an Ollama model
    """
    from ollama_client import list_models, is_running
    user_id = str(update.effective_user.id)

    if not context.args:
        backend, model = get_backend(user_id)
        label = f"Gemini (gemini-2.5-flash)" if backend == BACKEND_GEMINI else f"Ollama ({model})"
        ollama_status = "running ✓" if is_running() else "not running ✗"
        await update.message.reply_text(
            f"Current model: {label}\n"
            f"Ollama: {ollama_status}\n\n"
            f"Commands:\n"
            f"  /model gemini       → switch to Gemini\n"
            f"  /model llama3.1:8b  → switch to Ollama model\n"
            f"  /model list         → list local Ollama models"
        )
        return

    sub = context.args[0].lower()

    if sub == "list":
        if not is_running():
            await update.message.reply_text("Ollama is not running. Start it with: `ollama serve`")
            return
        models = list_models()
        if not models:
            await update.message.reply_text("No Ollama models found. Pull one with: `ollama pull llama3.1:8b`")
        else:
            await update.message.reply_text("Available Ollama models:\n" + "\n".join(f"• {m}" for m in models))
        return

    if sub == "gemini":
        set_config(user_id, "model", "gemini")
        await update.message.reply_text("Switched to Gemini (gemini-2.5-flash) ✓")
        return

    # Treat as Ollama model name
    model_name = context.args[0]   # preserve original casing
    if not is_running():
        await update.message.reply_text(
            f"Ollama is not running. Start it first:\n  ollama serve\nThen try again."
        )
        return
    available = list_models()
    if model_name not in available:
        available_str = "\n".join(f"• {m}" for m in available) if available else "  (none)"
        await update.message.reply_text(
            f"Model '{model_name}' not found locally.\n\n"
            f"Available:\n{available_str}\n\n"
            f"Pull it with: ollama pull {model_name}"
        )
        return
    set_config(user_id, "model", model_name)
    await update.message.reply_text(f"Switched to Ollama → {model_name} ✓")


async def handle_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    now = datetime.datetime.now()
    lines = [f"Good {'morning' if now.hour < 12 else 'afternoon' if now.hour < 18 else 'evening'}! Here's your brief.\n"]
    lines.append(f"📅 {now.strftime('%A, %d %B %Y — %I:%M %p IST')}\n")

    # Weather
    try:
        from weather import get_weather
        lines.append(f"🌤 Weather: {get_weather('Chennai')}")
    except Exception as e:
        lines.append(f"🌤 Weather: unavailable ({e})")

    # Emails
    try:
        from gmail import get_unread_emails
        emails = get_unread_emails(5)
        lines.append(f"\n📬 Unread emails: {len(emails)}")
        for e in emails[:3]:
            lines.append(f"  • {e['from'].split('<')[0].strip()} — {e['subject']}")
        if len(emails) > 3:
            lines.append(f"  ...and {len(emails) - 3} more")
    except Exception as e:
        lines.append(f"\n📬 Email: unavailable ({e})")

    # Upcoming reminders
    try:
        user_id = str(update.effective_user.id)
        reminders = list_upcoming(user_id, limit=3)
        if reminders:
            lines.append("\n⏰ Upcoming reminders:")
            for _, msg, fire_at in reminders:
                dt = datetime.datetime.fromisoformat(fire_at)
                lines.append(f"  • {dt.strftime('%I:%M %p')} — {msg}")
    except Exception:
        pass

    # Pending tasks
    try:
        tasks = [(tid, task) for tid, task, done in list_tasks(str(update.effective_user.id)) if not done]
        if tasks:
            lines.append(f"\n✅ Open tasks: {len(tasks)}")
            for tid, task in tasks[:3]:
                lines.append(f"  • {task}")
            if len(tasks) > 3:
                lines.append(f"  ...and {len(tasks) - 3} more")
    except Exception:
        pass

    await update.message.reply_text("\n".join(lines))

# ── /note ─────────────────────────────────────────────────────────────────────

async def handle_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    note    = " ".join(context.args)
    if note:
        save_note(user_id, note)
        await update.message.reply_text(f"Got it, I'll remember: {note}")
    else:
        await update.message.reply_text("Usage: /note your text here")

# ── /inbox ────────────────────────────────────────────────────────────────────

async def handle_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        from gmail import get_unread_emails, format_emails_for_maxy
        emails = get_unread_emails(5)
        await update.message.reply_text(format_emails_for_maxy(emails))
    except Exception as e:
        await update.message.reply_text(f"Could not fetch emails: {e}")

# ── /send ─────────────────────────────────────────────────────────────────────

async def handle_send_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args_text = " ".join(context.args)
        parts     = args_text.split("|")
        if len(parts) != 3:
            await update.message.reply_text(
                "Format: /send email@example.com | Subject | Body"
            )
            return
        to, subject, body = [p.strip() for p in parts]
        from gmail import send_email
        send_email(to, subject, body)
        await update.message.reply_text(f"Done! Email sent to {to}")
    except Exception as e:
        await update.message.reply_text(f"Failed to send: {e}")

# ── Inline buttons (email confirm) ────────────────────────────────────────────

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    data    = query.data

    if data.startswith("send_"):
        if user_id in pending_emails:
            email = pending_emails[user_id]
            try:
                from gmail import send_email
                send_email(email["to"], email["subject"], email["body"])
                await query.edit_message_text(f"Sent to {email['to']}!")
                del pending_emails[user_id]
            except Exception as e:
                await query.edit_message_text(f"Failed to send: {e}")
        else:
            await query.edit_message_text("No pending email found.")

    elif data.startswith("cancel_"):
        if user_id in pending_emails:
            del pending_emails[user_id]
        await query.edit_message_text("Email cancelled.")

# ── Reminder scheduler ────────────────────────────────────────────────────────

async def _fire_due_reminders(bot):
    rows = get_due_reminders()
    for rid, chat_id, message in rows:
        try:
            await bot.send_message(chat_id=int(chat_id), text=f"⏰ Reminder: {message}")
            mark_sent(rid)
        except Exception:
            pass

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    app   = ApplicationBuilder().token(token).build()

    # Scheduler — checks for due reminders every 30 seconds
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _fire_due_reminders,
        "interval",
        seconds=30,
        args=[app.bot],
        id="reminder_check"
    )
    scheduler.start()

    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("model",      handle_model))
    app.add_handler(CommandHandler("brief",      handle_brief))
    app.add_handler(CommandHandler("weather",    handle_weather))
    app.add_handler(CommandHandler("search",     handle_search))
    app.add_handler(CommandHandler("remind",     handle_remind))
    app.add_handler(CommandHandler("reminders",  handle_list_reminders))
    app.add_handler(CommandHandler("todo",       handle_todo))
    app.add_handler(CommandHandler("note",       handle_note))
    app.add_handler(CommandHandler("inbox",      handle_inbox))
    app.add_handler(CommandHandler("send",       handle_send_email))
    app.add_handler(CallbackQueryHandler(handle_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Maxy is alive on Telegram!")
    app.run_polling()

if __name__ == "__main__":
    main()

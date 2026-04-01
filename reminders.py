import sqlite3
import datetime
import os
import re
from maxy_home import DB_PATH

# ── DB ────────────────────────────────────────────────────────────────────────

def _init():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  TEXT NOT NULL,
            chat_id  TEXT NOT NULL,
            message  TEXT NOT NULL,
            fire_at  TEXT NOT NULL,
            sent     INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

# ── Parsing ───────────────────────────────────────────────────────────────────

_DURATION_RE = re.compile(
    r'^(\d+)\s*(s|sec|seconds?|m|min|minutes?|h|hr|hours?|d|days?)$',
    re.IGNORECASE
)

def parse_duration(s: str) -> datetime.timedelta | None:
    """'30m' -> timedelta(minutes=30), '2h' -> timedelta(hours=2), etc."""
    m = _DURATION_RE.match(s.strip())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    if unit.startswith('s'):
        return datetime.timedelta(seconds=n)
    if unit.startswith('m'):
        return datetime.timedelta(minutes=n)
    if unit.startswith('h'):
        return datetime.timedelta(hours=n)
    if unit.startswith('d'):
        return datetime.timedelta(days=n)
    return None

# ── CRUD ──────────────────────────────────────────────────────────────────────

def add_reminder(user_id: str, chat_id: str, message: str,
                 fire_at: datetime.datetime) -> int:
    _init()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO reminders (user_id, chat_id, message, fire_at) VALUES (?,?,?,?)",
        (user_id, chat_id, message, fire_at.isoformat())
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid

def get_due_reminders() -> list[tuple]:
    """Return reminders that are due and haven't been sent yet."""
    _init()
    conn = sqlite3.connect(DB_PATH)
    now = datetime.datetime.now().isoformat()
    rows = conn.execute(
        "SELECT id, chat_id, message FROM reminders WHERE fire_at <= ? AND sent = 0",
        (now,)
    ).fetchall()
    conn.close()
    return rows

def mark_sent(reminder_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()

def list_upcoming(user_id: str, limit: int = 5) -> list[tuple]:
    """Return upcoming (unsent) reminders for a user."""
    _init()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT id, message, fire_at FROM reminders
           WHERE user_id = ? AND sent = 0
           ORDER BY fire_at ASC LIMIT ?""",
        (user_id, limit)
    ).fetchall()
    conn.close()
    return rows

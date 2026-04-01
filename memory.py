import sqlite3
import datetime
import os
from maxy_home import DB_PATH

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   TEXT NOT NULL,
            role      TEXT NOT NULL,
            content   TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   TEXT NOT NULL,
            note      TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   TEXT NOT NULL,
            task      TEXT NOT NULL,
            done      INTEGER DEFAULT 0,
            timestamp TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config (
            user_id   TEXT NOT NULL,
            key       TEXT NOT NULL,
            value     TEXT NOT NULL,
            PRIMARY KEY (user_id, key)
        )
    """)
    conn.commit()
    return conn


# ── Config / preferences ──────────────────────────────────────────────────────

def set_config(user_id: str, key: str, value: str):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO config (user_id, key, value) VALUES (?, ?, ?)",
        (user_id, key, value)
    )
    conn.commit()
    conn.close()


def get_config(user_id: str, key: str, default: str = "") -> str:
    conn = get_db()
    row = conn.execute(
        "SELECT value FROM config WHERE user_id = ? AND key = ?",
        (user_id, key)
    ).fetchone()
    conn.close()
    return row[0] if row else default


# ── Tasks ─────────────────────────────────────────────────────────────────────

def save_task(user_id: str, task: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO tasks (user_id, task, timestamp) VALUES (?, ?, ?)",
        (user_id, task, datetime.datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def list_tasks(user_id: str) -> list:
    """Returns list of (id, task, done) ordered by id."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, task, done FROM tasks WHERE user_id = ? ORDER BY id ASC",
        (user_id,)
    ).fetchall()
    conn.close()
    return rows

def complete_task(user_id: str, task_id: int) -> bool:
    conn = get_db()
    cur = conn.execute(
        "UPDATE tasks SET done = 1 WHERE id = ? AND user_id = ?",
        (task_id, user_id)
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0

def delete_task(user_id: str, task_id: int) -> bool:
    conn = get_db()
    cur = conn.execute(
        "DELETE FROM tasks WHERE id = ? AND user_id = ?",
        (task_id, user_id)
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0

def save_message(user_id: str, role: str, content: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO messages (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (str(user_id), role, content, datetime.datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def load_history(user_id: str, limit: int = 30) -> list:
    conn = get_db()
    rows = conn.execute(
        """SELECT role, content FROM messages
           WHERE user_id = ?
           ORDER BY id DESC LIMIT ?""",
        (str(user_id), limit)
    ).fetchall()
    conn.close()
    return [{"role": r, "content": c} for r, c in reversed(rows)]

def save_note(user_id: str, note: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO notes (user_id, note, timestamp) VALUES (?, ?, ?)",
        (str(user_id), note, datetime.datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def load_notes(user_id: str) -> str:
    conn = get_db()
    rows = conn.execute(
        "SELECT note FROM notes WHERE user_id = ? ORDER BY id DESC LIMIT 20",
        (str(user_id),)
    ).fetchall()
    conn.close()
    if not rows:
        return ""
    return "\n".join(f"- {r[0]}" for r in rows)
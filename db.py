"""Tiny storage layer: Postgres if DATABASE_URL is set, otherwise SQLite."""
import os
import sqlite3

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_PG = bool(DATABASE_URL)

if USE_PG:
    import psycopg2
    PH = "%s"
    PK = "SERIAL PRIMARY KEY"
else:
    PH = "?"
    PK = "INTEGER PRIMARY KEY AUTOINCREMENT"


def _connect():
    if USE_PG:
        return psycopg2.connect(DATABASE_URL)
    return sqlite3.connect("history.db")


def _run(sql, params=(), fetch=False):
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(sql.replace("?", PH), params)
        rows = cur.fetchall() if fetch else None
        conn.commit()
        return rows
    finally:
        conn.close()


def init_db():
    _run(
        f"""CREATE TABLE IF NOT EXISTS messages (
            id {PK},
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL
        )"""
    )
    _run("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id)")


def save_message(session_id, role, content):
    _run(
        "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content),
    )


def get_history(session_id, limit=40):
    rows = _run(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, limit),
        fetch=True,
    )
    return [{"role": r, "content": c} for r, c in reversed(rows)]


def clear_history(session_id):
    _run("DELETE FROM messages WHERE session_id = ?", (session_id,))

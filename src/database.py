"""
src/database.py
───────────────
SQLite persistence layer.

Tables:
  emails        – deduplicated store of every fetched Gmail message
  deadlines     – one row per detected deadline per email
  notifications – audit log of every fired notification
  agent_memory  – stores agent conversation / thought history per session
"""
import hashlib
import logging
import sqlite3
from datetime import datetime
from typing import Optional

from config.settings import DB_PATH

logger = logging.getLogger(__name__)


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init_db() -> None:
    """Create all tables and indexes if they do not already exist."""
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS emails (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                gmail_message_id TEXT    UNIQUE NOT NULL,
                sender           TEXT    DEFAULT '',
                subject          TEXT    DEFAULT '',
                received_at      TEXT    DEFAULT '',
                body_hash        TEXT    DEFAULT '',
                scanned_at       TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS deadlines (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id      INTEGER NOT NULL REFERENCES emails(id),
                action_type   TEXT    NOT NULL,
                source_phrase TEXT    DEFAULT '',
                deadline_at   TEXT    NOT NULL,
                remind_at     TEXT    NOT NULL,
                confidence    REAL    DEFAULT 1.0,
                detected_by   TEXT    DEFAULT 'rule',
                status        TEXT    DEFAULT 'pending',
                snoozed_until TEXT,
                created_at    TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                deadline_id   INTEGER NOT NULL REFERENCES deadlines(id),
                fired_at      TEXT    NOT NULL,
                action        TEXT    DEFAULT 'notified',
                snoozed_until TEXT
            );

            CREATE TABLE IF NOT EXISTS agent_memory (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT    NOT NULL,
                role       TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                created_at TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_emails_msgid     ON emails(gmail_message_id);
            CREATE INDEX IF NOT EXISTS ix_deadlines_status ON deadlines(status);
            CREATE INDEX IF NOT EXISTS ix_deadlines_remind ON deadlines(remind_at);
            CREATE INDEX IF NOT EXISTS ix_memory_session   ON agent_memory(session_id);
        """)
    logger.debug("DB ready: %s", DB_PATH)


# ── Email helpers ─────────────────────────────────────────────────────────────

def body_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:20]


def email_exists(gid: str) -> bool:
    with _conn() as c:
        return c.execute(
            "SELECT 1 FROM emails WHERE gmail_message_id=?", (gid,)
        ).fetchone() is not None


def save_email(data: dict) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO emails"
            "(gmail_message_id,sender,subject,received_at,body_hash,scanned_at)"
            " VALUES(?,?,?,?,?,?)",
            (data["gmail_message_id"], data.get("sender", ""),
             data.get("subject", ""), data.get("received_at", ""),
             data.get("body_hash", ""), datetime.now().isoformat()),
        )
        if cur.lastrowid:
            return cur.lastrowid
        return c.execute(
            "SELECT id FROM emails WHERE gmail_message_id=?",
            (data["gmail_message_id"],)
        ).fetchone()["id"]


# ── Deadline helpers ──────────────────────────────────────────────────────────

def deadline_exists(email_id: int, action_type: str) -> bool:
    with _conn() as c:
        return c.execute(
            "SELECT 1 FROM deadlines WHERE email_id=? AND action_type=?",
            (email_id, action_type)
        ).fetchone() is not None


def save_deadline(data: dict) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO deadlines"
            "(email_id,action_type,source_phrase,deadline_at,remind_at,"
            "confidence,detected_by,status,created_at)"
            " VALUES(?,?,?,?,?,?,?,'pending',?)",
            (data["email_id"], data["action_type"],
             data.get("source_phrase", ""),
             data["deadline_at"].isoformat(),
             data["remind_at"].isoformat(),
             data.get("confidence", 1.0),
             data.get("detected_by", "rule"),
             datetime.now().isoformat()),
        )
    logger.info("Deadline saved [%s] dl=%s remind=%s",
                data["action_type"],
                data["deadline_at"].strftime("%Y-%m-%d"),
                data["remind_at"].strftime("%Y-%m-%d"))
    return cur.lastrowid


def get_due_reminders() -> list:
    """Return pending reminders whose remind_at <= now and not snoozed."""
    now = datetime.now().isoformat()
    with _conn() as c:
        rows = c.execute(
            "SELECT d.*,e.subject,e.sender,e.gmail_message_id"
            " FROM deadlines d JOIN emails e ON e.id=d.email_id"
            " WHERE d.status='pending' AND d.remind_at<=?"
            " AND (d.snoozed_until IS NULL OR d.snoozed_until<=?)"
            " ORDER BY d.deadline_at",
            (now, now)
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_pending() -> list:
    with _conn() as c:
        rows = c.execute(
            "SELECT d.*,e.subject,e.sender"
            " FROM deadlines d JOIN emails e ON e.id=d.email_id"
            " WHERE d.status='pending'"
            " ORDER BY d.deadline_at"
        ).fetchall()
    return [dict(r) for r in rows]


def mark_reminded(did: int) -> None:
    with _conn() as c:
        c.execute("UPDATE deadlines SET status='reminded' WHERE id=?", (did,))
    _log_notif(did, "notified")


def snooze_dl(did: int, until: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE deadlines SET snoozed_until=? WHERE id=?", (until, did)
        )
    _log_notif(did, "snoozed", until)


def dismiss_dl(did: int) -> None:
    with _conn() as c:
        c.execute("UPDATE deadlines SET status='dismissed' WHERE id=?", (did,))
    _log_notif(did, "dismissed")


def _log_notif(did: int, action: str, snoozed: Optional[str] = None):
    with _conn() as c:
        c.execute(
            "INSERT INTO notifications(deadline_id,fired_at,action,snoozed_until)"
            " VALUES(?,?,?,?)",
            (did, datetime.now().isoformat(), action, snoozed)
        )


# ── Agent memory ──────────────────────────────────────────────────────────────

def add_memory(session_id: str, role: str, content: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO agent_memory(session_id,role,content,created_at)"
            " VALUES(?,?,?,?)",
            (session_id, role, content, datetime.now().isoformat())
        )


def get_memory(session_id: str, last_n: int = 20) -> list:
    with _conn() as c:
        rows = c.execute(
            "SELECT role,content FROM agent_memory WHERE session_id=?"
            " ORDER BY created_at DESC LIMIT ?",
            (session_id, last_n)
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def clear_memory(session_id: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM agent_memory WHERE session_id=?", (session_id,))

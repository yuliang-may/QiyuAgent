"""SQLite session store for persistent conversation state.

Stores sessions and messages so users can resume interrupted conversations.
Uses aiosqlite for async SQLite access.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    context_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    role TEXT NOT NULL,
    content TEXT DEFAULT '',
    tool_name TEXT DEFAULT '',
    tool_args TEXT DEFAULT '',
    tool_result TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
"""


class SessionStore:
    """Async SQLite session store."""

    def __init__(self, db_path: str | Path = "lacquertutor.db") -> None:
        self.db_path = str(db_path)
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Open database and create tables if needed."""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA_SQL)
        await self._db.commit()
        logger.info("Session store initialized: %s", self.db_path)

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def create_session(self, user_id: str = "") -> str:
        """Create a new session. Returns the session_id."""
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO sessions (session_id, user_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, user_id, now, now),
        )
        await self._db.commit()
        logger.info("Created session %s", session_id)
        return session_id

    async def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        display_name: str = "",
    ) -> dict[str, Any]:
        """Create a user account and return the stored record."""
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO users (user_id, username, password_hash, display_name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, password_hash, display_name, now, now),
        )
        await self._db.commit()
        user = await self.get_user_by_id(user_id)
        if user is None:
            raise RuntimeError("failed to fetch created user")
        return user

    async def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        cursor = await self._db.execute(
            "SELECT * FROM users WHERE lower(username) = lower(?)",
            (username,),
        )
        row = await cursor.fetchone()
        return dict(row) if row is not None else None

    async def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        cursor = await self._db.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row is not None else None

    async def list_user_sessions(self, user_id: str, limit: int = 6) -> list[dict[str, Any]]:
        return await self.list_sessions(user_id=user_id, limit=limit)

    async def count_sessions_for_user(self, user_id: str) -> int:
        cursor = await self._db.execute(
            "SELECT COUNT(*) AS total FROM sessions WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        return int(row["total"]) if row is not None else 0

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session details. Returns None if not found."""
        cursor = await self._db.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def update_context(self, session_id: str, context_json: str) -> None:
        """Update the serialized context for a session."""
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "UPDATE sessions SET context_json = ?, updated_at = ? WHERE session_id = ?",
            (context_json, now, session_id),
        )
        await self._db.commit()

    async def update_status(self, session_id: str, status: str) -> None:
        """Update session status (active/completed/abandoned)."""
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "UPDATE sessions SET status = ?, updated_at = ? WHERE session_id = ?",
            (status, now, session_id),
        )
        await self._db.commit()

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str = "",
        tool_name: str = "",
        tool_args: str = "",
        tool_result: str = "",
    ) -> int:
        """Add a message to a session. Returns message_id."""
        cursor = await self._db.execute(
            "INSERT INTO messages (session_id, role, content, tool_name, tool_args, tool_result) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, role, content, tool_name, tool_args, tool_result),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Get all messages for a session, ordered by creation time."""
        cursor = await self._db.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY message_id",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def list_sessions(
        self, user_id: str | None = None, status: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List sessions with optional filtering."""
        conditions = []
        params = []
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        cursor = await self._db.execute(
            f"SELECT * FROM sessions{where} ORDER BY updated_at DESC LIMIT ?",
            params,
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def delete_session(self, session_id: str) -> None:
        """Delete a session and its messages."""
        await self._db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        await self._db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        await self._db.commit()

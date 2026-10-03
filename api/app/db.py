"""Tiny SQLite store with JSON columns. No ORM needed for a hackathon MVP."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

DATA_DIR = Path(os.environ.get("SKYMENTOR_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DB_PATH = Path(os.environ.get("SKYMENTOR_DB", DATA_DIR / "skymentor.db"))

_lock = threading.RLock()
_conn: Optional[sqlite3.Connection] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, mode TEXT, created REAL, case_json TEXT,
  expert_session_id TEXT, state_json TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY, session_id TEXT, ts REAL, type TEXT, option_id TEXT,
  detail_json TEXT, snapshot_json TEXT, off_record INTEGER, score_json TEXT
);
CREATE TABLE IF NOT EXISTS transcript (
  id TEXT PRIMARY KEY, session_id TEXT, ts REAL, role TEXT, text TEXT, off_record INTEGER
);
CREATE TABLE IF NOT EXISTS questions (
  id TEXT PRIMARY KEY, session_id TEXT, event_id TEXT, created_ts REAL, asked_ts REAL,
  text TEXT, category TEXT, is_guardrail INTEGER, phase TEXT, answered INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS rules (
  id TEXT PRIMARY KEY, session_id TEXT, json TEXT
);
CREATE TABLE IF NOT EXISTS interventions (
  id TEXT PRIMARY KEY, session_id TEXT, ts REAL, json TEXT
);
"""


def conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.executescript(SCHEMA)
        return _conn


def reset() -> None:
    with _lock:
        c = conn()
        for table in ("sessions", "events", "transcript", "questions", "rules", "interventions"):
            c.execute(f"DELETE FROM {table}")
        c.commit()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def execute(sql: str, params: tuple = ()) -> None:
    with _lock:
        c = conn()
        c.execute(sql, params)
        c.commit()


def query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with _lock:
        rows = conn().execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def one(sql: str, params: tuple = ()) -> Optional[dict[str, Any]]:
    rows = query(sql, params)
    return rows[0] if rows else None


def dumps(obj: Any) -> str:
    return json.dumps(obj, default=str)


def loads(s: Optional[str], default: Any = None) -> Any:
    if not s:
        return default
    return json.loads(s)


# ------------------------------------------------------------------ session clock
def session_row(session_id: str) -> dict[str, Any]:
    row = one("SELECT * FROM sessions WHERE id=?", (session_id,))
    if row is None:
        raise KeyError(session_id)
    return row


def session_ts(session_id: str) -> float:
    """Single session clock: seconds since the session started (server time)."""
    return round(time.time() - session_row(session_id)["created"], 1)


def get_state(session_id: str) -> dict[str, Any]:
    return loads(session_row(session_id)["state_json"], {})


def set_state(session_id: str, state: dict[str, Any]) -> None:
    execute("UPDATE sessions SET state_json=? WHERE id=?", (dumps(state), session_id))


def fmt_ts(ts: Optional[float]) -> str:
    if ts is None:
        return "--:--"
    m, s = divmod(int(ts), 60)
    return f"{m:02d}:{s:02d}"

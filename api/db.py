"""SQLite 연결·초기화 (docs/db-schema.md 참조).

Phase 4-b: 연결·스키마 생성 + users 테이블만 실사용.
           session/answer/complete/history는 아직 메모리 방식 그대로 (Phase 4-c).

★ SQL은 반드시 파라미터화 쿼리(placeholder `?`)로 쓴다. 문자열 이어붙이기 금지
  (SQL 인젝션 방지 — 절대 규칙).
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "dementia.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id    TEXT PRIMARY KEY,
    level      INTEGER NOT NULL DEFAULT 1,
    week       INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_completions (
    user_id      TEXT NOT NULL,
    date         TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    UNIQUE (user_id, date)
);

CREATE TABLE IF NOT EXISTS session_progress (
    session_id          TEXT NOT NULL,
    user_id              TEXT NOT NULL,
    consecutive_correct  INTEGER NOT NULL DEFAULT 0,
    consecutive_wrong    INTEGER NOT NULL DEFAULT 0
);
"""


def get_connection() -> sqlite3.Connection:
    """요청마다 새 커넥션을 연다 (SQLite는 짧은 커넥션에 적합, 커넥션 풀 불필요)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """docs/db-schema.md의 3테이블을 CREATE TABLE IF NOT EXISTS로 생성."""
    with get_connection() as conn:
        conn.executescript(_SCHEMA)

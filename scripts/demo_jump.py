#!/usr/bin/env python3
"""데모용 — 사용자를 원하는 주차/일차/레벨로 즉시 옮긴다.

왜 필요한가: week/day는 `daily_completions` 완료 개수 N으로 파생된다
(`api-spec.md` §3.1). 그래서 4주차 화면을 보려면 원래 16일을 기다려야 한다.
이 스크립트는 과거 날짜 완료 기록을 N개 채워 넣어 그 지점으로 건너뛴다.

★ 운영 DB는 건드릴 수 없다 — 운영 데이터는 도커 named volume 안에 있고,
  이 스크립트는 호스트의 데모 파일(기본 api/data/demo.db)만 연다.

사용법:
    python3 scripts/demo_jump.py --week 4 --day 2 --level 3
    python3 scripts/demo_jump.py --week 1 --day 1 --level 1 --list

오늘 날짜는 비워 두므로(과거 날짜만 채운다) 실행 직후 바로 오늘 세션을 할 수 있다.
같은 날 두 번째 세션이 막혔을 때(409) 다시 돌리면 풀린다.
"""

import argparse
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO / "api" / "data" / "demo.db"
DAYS_PER_WEEK = 5  # api-spec.md §3.1: week = N//5 + 1


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        sys.exit(
            f"데모 DB가 없습니다: {db_path}\n"
            "  → scripts/demo.sh 로 서버를 띄우고, 브라우저에서 http://localhost:3000 을\n"
            "     한 번 열어 사용자를 발급받은 뒤 다시 실행하세요."
        )
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def pick_user(conn: sqlite3.Connection, user_id: str | None) -> str:
    rows = conn.execute(
        "SELECT user_id, level, created_at FROM users ORDER BY created_at DESC"
    ).fetchall()
    if not rows:
        sys.exit(
            "데모 DB에 사용자가 없습니다.\n"
            "  → 브라우저에서 http://localhost:3000 을 한 번 열면 자동 발급됩니다."
        )
    if user_id:
        if user_id not in {r["user_id"] for r in rows}:
            sys.exit(f"그런 user_id가 없습니다: {user_id}")
        return user_id
    if len(rows) > 1:
        print(f"※ 사용자가 {len(rows)}명입니다. 가장 최근 발급자를 씁니다 "
              f"(다른 사람을 쓰려면 --user-id).")
    return rows[0]["user_id"]


def jump(conn: sqlite3.Connection, user_id: str, target_n: int, level: int) -> None:
    """완료 기록을 정확히 target_n개로 다시 깐다. 전부 과거 날짜라 오늘은 비어 있다."""
    today = date.today()
    conn.execute("DELETE FROM daily_completions WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM session_progress WHERE user_id = ?", (user_id,))
    for i in range(target_n):
        d = (today - timedelta(days=target_n - i)).isoformat()
        conn.execute(
            "INSERT INTO daily_completions (user_id, date, completed_at) VALUES (?, ?, ?)",
            (user_id, d, f"{d}T09:00:00"),
        )
    conn.execute("UPDATE users SET level = ? WHERE user_id = ?", (level, user_id))
    conn.commit()


def main() -> None:
    ap = argparse.ArgumentParser(description="데모용 주차/일차/레벨 점프")
    ap.add_argument("--week", type=int, default=1, help="목표 주차 (1부터)")
    ap.add_argument("--day", type=int, default=1, help="목표 일차 (1~5)")
    ap.add_argument("--level", type=int, default=2, choices=(1, 2, 3), help="난이도 (기본 2)")
    ap.add_argument("--user-id", default=None, help="대상 사용자 (기본: 가장 최근 발급자)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"DB 파일 (기본 {DEFAULT_DB})")
    ap.add_argument("--list", action="store_true", help="사용 가능한 주차 목록도 출력")
    args = ap.parse_args()

    if not 1 <= args.day <= DAYS_PER_WEEK:
        sys.exit(f"--day 는 1~{DAYS_PER_WEEK} 여야 합니다 (받은 값: {args.day})")
    if args.week < 1:
        sys.exit(f"--week 는 1 이상이어야 합니다 (받은 값: {args.week})")

    weeks = sorted(
        int(p.stem.removeprefix("questions-week"))
        for p in (REPO / "content").glob("questions-week*.json")
    )
    if args.list:
        print(f"콘텐츠가 있는 주차: {weeks}")
    if args.week not in weeks:
        print(f"※ {args.week}주차 콘텐츠 파일이 없습니다. 서버가 마지막 주차"
              f"({max(weeks)}주차)로 clamp 합니다 — 의도된 fallback입니다.")

    conn = connect(args.db)
    user_id = pick_user(conn, args.user_id)
    target_n = (args.week - 1) * DAYS_PER_WEEK + (args.day - 1)
    jump(conn, user_id, target_n, args.level)

    # 방금 쓴 값을 다시 읽어 확인한다 (썼다고 보고만 하고 실제로는 비어 있는 사고 방지).
    n = conn.execute(
        "SELECT COUNT(*) FROM daily_completions WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    lv = conn.execute(
        "SELECT level FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    conn.close()

    if n != target_n or lv != args.level:
        sys.exit(f"ABORT: 기록 후 확인 실패 (N={n}/{target_n}, level={lv}/{args.level})")

    print(f"완료 — user {user_id[:8]}… → {args.week}주차 {args.day}일차, 레벨 {lv} "
          f"(N={n}, 오늘은 비어 있음)")
    print("  브라우저에서 새로고침하면 반영됩니다.")


if __name__ == "__main__":
    main()

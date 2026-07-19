"""dementia-care API (FastAPI).

api-spec §0.1: 브라우저는 /api/py/* 를 호출하고, Next.js rewrites가 '/api/py'
접두어를 떼어 이 서버의 /* 로 중계한다. 따라서 이 서버는 접두어 없이 서빙한다.

Phase 2-b-1: 판정 없는 엔드포인트 3개 (users, session/today, history).
Phase 2-b-2: 판정 있는 엔드포인트 2개 (answer, complete).
             로직은 실제로 짜고 문항 데이터는 content/questions-week1.json 에서 읽는다.
             DB는 없다 (Phase 4에서 붙음). answer(정답)·점수는 절대 응답에 넣지 않는다.
             시도 횟수·연속 성공/실패는 프로세스 메모리에 보관 (재시작하면 초기화 — 지금은 허용).

로컬 확인: uvicorn index:app --host 127.0.0.1 --port 8000
"""

import hashlib
import json
import logging
import random
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import db

app = FastAPI(title="dementia-care API")
logger = logging.getLogger("uvicorn.error")

# docs/db-schema.md의 3테이블 생성 (Phase 4-b: users만 실사용, 나머지는 4-c).
# 모듈은 프로세스당 한 번만 로드되므로 여기서 바로 실행한다.
db.init_db()

# ── 문항 데이터 (DB 대신 파일에서 로드) ────────────────────────────
CONTENT_PATH = Path(__file__).resolve().parent.parent / "content" / "questions-week1.json"
with CONTENT_PATH.open(encoding="utf-8") as f:
    CONTENT = json.load(f)

# Mon=0 … Sun=6 (date.weekday()와 정렬)
WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

# ── 임시 상태 저장 (DB 미이관분만, Phase 4-c-3에서 session_progress로 옮김) ──
# 서버 재시작하면 초기화된다 — 지금은 허용. level은 Phase 4-c-1/4-c-2부터 DB가
# 유일한 출처라 여기엔 안 둔다 (consecutive_correct/wrong만 메모리에 남음).
_attempts: dict[tuple[int, int], int] = {}  # (session_id, question_id) -> 시도 횟수
_streaks: dict[str, dict] = {}  # user_id -> {"consecutive_correct", "consecutive_wrong"}


# ── 에러 체계 (api-spec §0.4) ─────────────────────────────────────
class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


@app.exception_handler(ApiError)
async def _api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(Exception)
async def _unhandled_handler(request: Request, exc: Exception):
    logger.exception("unhandled error")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "잠깐 문제가 생겼어요. 다시 해보세요",
            }
        },
    )


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def require_user_id(x_user_id: str | None = Header(default=None, alias="X-User-Id")) -> str:
    # §0.3: X-User-Id 가 없거나 형식이 틀리면 401 NO_USER_ID
    if not x_user_id or not _is_uuid(x_user_id):
        raise ApiError(401, "NO_USER_ID", "누구신지 확인하지 못했어요. 다시 시작해 주세요")
    return x_user_id


def get_user_level(user_id: str) -> int:
    """users 테이블에서 level을 조회한다 (파라미터화 쿼리).
    형식은 맞지만(UUID) 우리 시스템에 없는 user_id — 발급받은 적 없거나 DB가
    초기화된 경우다. NO_USER_ID와 같은 401로 응답한다: 클라이언트 입장에서
    "이 헤더로는 누구인지 확인 못 했다"는 사실은 헤더가 없을 때와 동일하고,
    처리 방법도 같다 (POST /users로 다시 발급받아 재시작)."""
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT level FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    if row is None:
        raise ApiError(401, "NO_USER_ID", "누구신지 확인하지 못했어요. 다시 시작해 주세요")
    return row["level"]


# ── 결정적 셔플 (api-spec §0.5) ───────────────────────────────────
def deterministic_shuffle(items: list, *seed_parts) -> list:
    """session_id+question_id 씨앗으로 매번 같은 순서. 새로고침해도 안 바뀐다.
    문항 은행 저장순(정답이 앞쪽에 몰림)을 그대로 내보내지 않기 위함."""
    raw = ":".join(str(p) for p in seed_parts).encode()
    seed = int(hashlib.sha256(raw).hexdigest(), 16)
    out = list(items)
    random.Random(seed).shuffle(out)
    return out


def derive_session_id(user_id: str, day: date) -> int:
    """DB가 없어도 '같은 사용자·같은 날 = 같은 세션 = 같은 셔플'이 되도록
    session_id를 결정적으로 파생. Phase 4에서 DB의 실제 세션 PK로 대체."""
    h = hashlib.sha256(f"{user_id}:{day.isoformat()}".encode()).hexdigest()
    return int(h[:8], 16)


def build_weekday_step(qid: int, prompt: str, today: date, session_id: int) -> dict:
    """dynamic 요일 문항(level 2 warmup). 오늘 날짜로 정답+인접 요일 3개를 만들고
    결정적으로 섞는다. 정답이 무엇인지는 응답에 넣지 않는다."""
    idx = today.weekday()
    correct = WEEKDAYS[idx]
    neighbors = [WEEKDAYS[(idx + off) % 7] for off in (-1, 1, 2)]
    choices = deterministic_shuffle([correct, *neighbors], session_id, qid)
    return {"question_id": qid, "prompt": prompt, "choices": choices}


# ── 판정 (api-spec §4) ────────────────────────────────────────────
def find_question(question_id: int) -> dict | None:
    """questions-week1.json 전체(모든 요일·레벨)에서 question_id로 문항 정의를 찾는다.
    지금 /session/today가 실제로 내보내는 건 day1·level2뿐이지만, 판정 로직 자체는
    파일에 있는 answer_rule 전 종류를 지원해야 하므로 전체를 뒤진다."""
    for w in CONTENT["common"]["warmup"].values():
        # "_note" 같은 설명용 문자열 키가 섞여 있어 dict인 것만 본다.
        if isinstance(w, dict) and w.get("id") == question_id:
            return w
    for day in CONTENT["days"]:
        for q in day["main"].values():
            if isinstance(q, dict) and q.get("id") == question_id:
                return q
    return None


def _season_of(month: int) -> str:
    if month in (3, 4, 5):
        return "봄"
    if month in (6, 7, 8):
        return "여름"
    if month in (9, 10, 11):
        return "가을"
    return "겨울"


def _next_season(season: str) -> str:
    order = ["봄", "여름", "가을", "겨울"]
    return order[(order.index(season) + 1) % 4]


def compute_dynamic_answer(rule: str, today: date) -> str:
    """dynamic 문항의 answer_rule대로 오늘 날짜 기준 정답을 서버가 계산한다
    (questions-week1.json의 answer_rule 어휘 전부 지원)."""
    if rule == "weekday_type":
        return "주말" if today.weekday() >= 5 else "평일"
    if rule == "weekday":
        return WEEKDAYS[today.weekday()]
    if rule.startswith("weekday_offset:"):
        offset = int(rule.split(":", 1)[1])
        return WEEKDAYS[(today.weekday() + offset) % 7]
    if rule == "month_day":
        return f"{today.month}월 {today.day}일"
    if rule == "month":
        return f"{today.month}월"
    if rule == "year":
        return f"{today.year}년"
    if rule == "season":
        return _season_of(today.month)
    if rule == "season_next":
        return _next_season(_season_of(today.month))
    if rule == "season_temp":
        season = _season_of(today.month)
        if season == "여름":
            return "더운 계절"
        if season == "겨울":
            return "추운 계절"
        # 파일의 _note대로 봄·가을엔 이 문항 자체를 안 쓴다 (1224로 대체). 여기 온 건 이례적.
        raise ApiError(500, "INTERNAL_ERROR", "잠깐 문제가 생겼어요. 다시 해보세요")
    raise ApiError(500, "INTERNAL_ERROR", "잠깐 문제가 생겼어요. 다시 해보세요")


def judge(question: dict, response: str, today: date) -> bool:
    """정답 판정은 서버에서만 (api-spec §0.5). 정답 값 자체는 반환하지 않는다."""
    if question["answer_type"] == "static":
        return response == question["answer"]
    return response == compute_dynamic_answer(question["answer_rule"], today)


def _record_outcome(user_id: str, *, success: bool) -> None:
    """문항의 '최종' 결과(재시도 중이 아닌)만 연속 성공/실패에 반영한다."""
    s = _streaks.setdefault(user_id, {"consecutive_correct": 0, "consecutive_wrong": 0})
    if success:
        s["consecutive_correct"] += 1
        s["consecutive_wrong"] = 0
    else:
        s["consecutive_wrong"] += 1
        s["consecutive_correct"] = 0


# ── 도장판·연속 참여일 (daily_completions, api-spec §5·§6) ─────────
def get_completed_dates(user_id: str) -> set[str]:
    """이 사용자가 완료한 모든 날짜(YYYY-MM-DD)를 daily_completions에서 조회."""
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT date FROM daily_completions WHERE user_id = ?", (user_id,)
        ).fetchall()
    return {row["date"] for row in rows}


def compute_streak_days(completed_dates: set[str], today: date) -> int:
    """오늘부터 거꾸로 세어 연속으로 완료한 날 수. 하루라도 빠지면 그 자리에서 멈춘다."""
    streak = 0
    d = today
    while d.isoformat() in completed_dates:
        streak += 1
        d -= timedelta(days=1)
    return streak


def record_completion(user_id: str, today: date) -> None:
    """오늘 완료를 daily_completions에 기록.

    (user_id, date) 유일 제약이라 같은 날 두 번째 완료는 막힌다. 조용히 무시하지
    않고 409 ALREADY_COMPLETED로 응답한다 — session_id가 user_id+날짜로 결정적으로
    파생되므로(Phase 2-b-1 derive_session_id), '같은 날 재완료'는 곧 '같은 세션 재완료'와
    같은 사건이고, api-spec §5가 이미 그 상황을 위한 코드를 정의해뒀다. 조용히
    무시하면 클라이언트가 실수로(예: 중복 클릭) 두 번 보냈을 때도 매번 '성공'
    응답을 받아 상태 착오를 못 알아챈다."""
    with db.get_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO daily_completions (user_id, date, completed_at) VALUES (?, ?, ?)",
                (user_id, today.isoformat(), datetime.now().isoformat()),
            )
        except sqlite3.IntegrityError:
            raise ApiError(409, "ALREADY_COMPLETED", "오늘은 이미 완료했어요")


def update_user_level(user_id: str, level: int) -> None:
    with db.get_connection() as conn:
        conn.execute("UPDATE users SET level = ? WHERE user_id = ?", (level, user_id))


class AnswerRequest(BaseModel):
    question_id: int
    response: str


class CompleteRequest(BaseModel):
    mood: str | None = None


# ── 엔드포인트 ────────────────────────────────────────────────────
@app.get("/health")
def health():
    # api-spec §7. Phase 2-a는 DB 미연결 — db는 하드코딩 "ok" (Phase 4에서 실제 점검).
    return {"status": "ok", "db": "ok"}


@app.post("/users", status_code=201)
def create_user():
    # §2. 익명 UUID를 발급하고 users 테이블에 저장한다 (Phase 4-b: 진짜 저장).
    # 파라미터화 쿼리(?)만 쓴다 — 문자열 이어붙이기 금지 (SQL 인젝션 방지, 절대 규칙).
    user_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO users (user_id, level, week, created_at) VALUES (?, ?, ?, ?)",
            (user_id, 1, 1, created_at),
        )
    return {"user_id": user_id, "level": 1, "week": 1}


@app.get("/session/today")
def session_today(user_id: str = Depends(require_user_id)):
    # §3. day 1 문항을 파일에서 읽어 5단계 구성. answer 절대 미포함.
    today = date.today()
    session_id = derive_session_id(user_id, today)
    day = CONTENT["days"][0]
    common = CONTENT["common"]
    level = get_user_level(user_id)

    # mood: 판정 없음 + 정서 척도(좋아요→별로예요)라 순서 유지 (셔플 안 함)
    mood = {
        "prompt": common["mood"]["prompt"],
        "choices": list(common["mood"]["choices"]),
    }

    # warmup(level 2 = dynamic 요일 문항): 오늘 날짜로 생성 + 결정적 셔플
    w = common["warmup"][str(level)]
    warmup = build_weekday_step(w["id"], w["prompt"], today, session_id)

    # main(level 2 = static): 파일 choices를 결정적 셔플, answer 제거
    m = day["main"][str(level)]
    main = {
        "question_id": m["id"],
        "prompt": m["prompt"],
        "choices": deterministic_shuffle(m["choices"], session_id, m["id"]),
    }

    # recall: 판정 없는 회상 질문 (question_id 없음)
    recall = {"prompt": day["recall"]["prompt"]}
    mission = {"text": day["mission"]["text"]}

    return {
        "session_id": session_id,
        "date": today.isoformat(),
        "week": CONTENT["week"],
        "domain": CONTENT["domain"],
        "level": level,
        "completed": False,
        "steps": {
            "mood": mood,
            "warmup": warmup,
            "main": main,
            "recall": recall,
            "mission": mission,
        },
    }


@app.get("/history")
def history(user_id: str = Depends(require_user_id)):
    # §6. 도장판은 '했다/안 했다'만. 정답률·점수는 절대 넣지 않는다.
    # daily_completions에서 실제 집계 (Phase 4-c-2, 고정 샘플 제거).
    today = date.today()
    completed_dates = get_completed_dates(user_id)
    streak_days = compute_streak_days(completed_dates, today)

    days = []
    for i in range(7):
        d = today - timedelta(days=6 - i)
        done = d.isoformat() in completed_dates
        days.append(
            {
                "date": d.isoformat(),
                "completed": done,
                "domain": CONTENT["domain"] if done else None,
            }
        )
    return {"streak_days": streak_days, "days": days}


@app.post("/session/{session_id}/answer")
def submit_answer(
    session_id: int,
    body: AnswerRequest,
    user_id: str = Depends(require_user_id),
):
    # §4. warmup·main만 호출. 정답 값은 응답에 절대 넣지 않는다 (§3.4/§0.5).
    question = find_question(body.question_id)
    if question is None:
        raise ApiError(404, "QUESTION_NOT_FOUND", "문항을 찾지 못했어요")

    key = (session_id, body.question_id)
    attempt = _attempts.get(key, 0) + 1
    _attempts[key] = attempt

    correct = judge(question, body.response, date.today())
    messages = CONTENT["common"]["messages"]

    if correct:
        # 1차든 2차 시도든, 맞으면 성공 — 재시도 규칙과 무관하게 바로 통과.
        _record_outcome(user_id, success=True)
        return {
            "correct": True,
            "attempts": attempt,
            "message": messages["correct"],
            "next_action": "proceed",
        }

    if attempt >= 2:
        # 2차 오답 → 최종 실패. 정답은 끝까지 알려주지 않는다.
        _record_outcome(user_id, success=False)
        return {
            "correct": False,
            "attempts": attempt,
            "message": messages["wrong_second"],
            "next_action": "proceed",
        }

    # 1차 오답 → 재시도 대기. 최종 결과가 아니므로 연속 성공/실패에 반영하지 않는다.
    return {
        "correct": False,
        "attempts": attempt,
        "message": messages["wrong_first"],
        "next_action": "retry",
    }


@app.post("/session/{session_id}/complete")
def complete_session(
    session_id: int,
    body: CompleteRequest,
    user_id: str = Depends(require_user_id),
):
    today = date.today()
    # 오늘 완료를 daily_completions에 기록 (같은 날 재완료는 409 ALREADY_COMPLETED).
    record_completion(user_id, today)

    # §5. 3연속 성공 → 상승 / 2연속 실패 → 하강 (PRD §3.3). 여기서만 난이도가 바뀐다.
    # consecutive_correct/wrong은 아직 메모리(Phase 4-c-3에서 session_progress로 이관).
    # level 자체는 Phase 4-c-1부터 DB가 유일한 출처 — 여기서도 DB에서 읽고 DB에 쓴다.
    s = _streaks.setdefault(user_id, {"consecutive_correct": 0, "consecutive_wrong": 0})
    level = get_user_level(user_id)
    next_level = level

    if s["consecutive_correct"] >= 3:
        next_level = min(level + 1, 3)
        s["consecutive_correct"] = 0
    elif s["consecutive_wrong"] >= 2:
        next_level = max(level - 1, 1)
        s["consecutive_wrong"] = 0

    level_changed = next_level != level
    if level_changed:
        update_user_level(user_id, next_level)

    # streak_days: daily_completions에서 실제 집계 (Phase 4-c-2, 고정 샘플 제거).
    completed_dates = get_completed_dates(user_id)
    streak_days = compute_streak_days(completed_dates, today)
    mission = CONTENT["days"][0]["mission"]["text"]
    message = (
        f"{streak_days}일째 연속이에요. 대단하세요!"
        if streak_days > 1
        else "오늘도 잘하셨어요!"
    )

    return {
        "session_id": session_id,
        "streak_days": streak_days,
        "next_level": next_level,
        "level_changed": level_changed,
        "mission": mission,
        "message": message,
    }

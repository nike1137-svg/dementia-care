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
import uuid
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="dementia-care API")
logger = logging.getLogger("uvicorn.error")

# ── 문항 데이터 (DB 대신 파일에서 로드) ────────────────────────────
CONTENT_PATH = Path(__file__).resolve().parent.parent / "content" / "questions-week1.json"
with CONTENT_PATH.open(encoding="utf-8") as f:
    CONTENT = json.load(f)

# 임시: DB 없어 사용자별 레벨 조회 불가. Phase 4에서 users.level로 대체. docs/decisions.md 참조
DEFAULT_LEVEL = 2

# Mon=0 … Sun=6 (date.weekday()와 정렬)
WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

# ── 임시 상태 저장 (Phase 2, DB 없음) ──────────────────────────────
# 서버 재시작하면 초기화된다 — 지금은 허용 (Phase 4에서 SQLite로 대체).
_attempts: dict[tuple[int, int], int] = {}  # (session_id, question_id) -> 시도 횟수
_streaks: dict[str, dict] = {}  # user_id -> {"level", "consecutive_correct", "consecutive_wrong"}

# history의 고정 샘플과 별개로, complete()의 streak_days '계산 로직'을 실제로 검증하기
# 위한 최근 6일(오늘 제외) 참여 샘플. 오늘(방금 완료)을 붙여 연속일을 실제로 센다.
PAST_DAYS_SAMPLE = [True, True, False, True, True, True]  # day-6 … day-1


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
    s = _streaks.setdefault(
        user_id, {"level": DEFAULT_LEVEL, "consecutive_correct": 0, "consecutive_wrong": 0}
    )
    if success:
        s["consecutive_correct"] += 1
        s["consecutive_wrong"] = 0
    else:
        s["consecutive_wrong"] += 1
        s["consecutive_correct"] = 0


def compute_streak_days(past_completed: list[bool], today_completed: bool) -> int:
    """오늘을 포함해 뒤에서부터 연속 완료일 수를 센다. (PRD §... 연속 참여일)"""
    full = [*past_completed, today_completed]
    streak = 0
    for done in reversed(full):
        if not done:
            break
        streak += 1
    return streak


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
    # §2. DB가 없어 발급만 한다 (Phase 4에서 저장). 익명 UUID.
    return {"user_id": str(uuid.uuid4()), "level": 1, "week": 1}


@app.get("/session/today")
def session_today(user_id: str = Depends(require_user_id)):
    # §3. day 1 문항을 파일에서 읽어 5단계 구성. answer 절대 미포함.
    today = date.today()
    session_id = derive_session_id(user_id, today)
    day = CONTENT["days"][0]
    common = CONTENT["common"]
    level = DEFAULT_LEVEL

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
    # DB가 없어 고정 샘플 패턴으로 형태만 (Phase 4에서 실제 조회). 날짜는 최근 7일.
    today = date.today()
    pattern = [True, True, False, True, True, True, False]
    days = []
    for i in range(7):
        d = today - timedelta(days=6 - i)
        done = pattern[i]
        days.append(
            {
                "date": d.isoformat(),
                "completed": done,
                "domain": CONTENT["domain"] if done else None,
            }
        )
    return {"streak_days": 5, "days": days}


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
    # §5. 3연속 성공 → 상승 / 2연속 실패 → 하강 (PRD §3.3). 여기서만 난이도가 바뀐다.
    s = _streaks.setdefault(
        user_id, {"level": DEFAULT_LEVEL, "consecutive_correct": 0, "consecutive_wrong": 0}
    )
    level = s["level"]
    next_level = level

    if s["consecutive_correct"] >= 3:
        next_level = min(level + 1, 3)
        s["consecutive_correct"] = 0
    elif s["consecutive_wrong"] >= 2:
        next_level = max(level - 1, 1)
        s["consecutive_wrong"] = 0

    level_changed = next_level != level
    s["level"] = next_level

    # streak_days: DB 없어 '이전 기록'은 고정 샘플이지만, 오늘 완료를 더해 연속일을
    # 세는 로직 자체는 실제로 돈다 (완전 하드코딩 아님).
    streak_days = compute_streak_days(PAST_DAYS_SAMPLE, today_completed=True)
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

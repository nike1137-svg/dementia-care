"""dementia-care API (FastAPI).

api-spec §0.1: 브라우저는 /api/py/* 를 호출하고, Next.js rewrites가 '/api/py'
접두어를 떼어 이 서버의 /* 로 중계한다. 따라서 이 서버는 접두어 없이 서빙한다.

Phase 2-b-1: 판정 없는 엔드포인트 3개 (users, session/today, history).
Phase 2-b-2: 판정 있는 엔드포인트 2개 (answer, complete).
             로직은 실제로 짜고 문항 데이터는 content/questions-week*.json 에서 읽는다.
             answer(정답)·점수는 절대 응답에 넣지 않는다.
Phase 4:     users·daily_completions·session_progress를 SQLite로 이관 완료.
             메모리에 남은 건 attempts(세션 내 시도 횟수, 의도적 유지)뿐이다.
2주차:       day/week 순환을 daily_completions 완료 개수로 파생 (resolve_progress).
             파일만 추가하면 새 주차가 자동 인식된다 (content_for_week).

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
# content/questions-week*.json을 전부 스캔해 주차별로 적재한다. day/week 순환은
# daily_completions 완료 개수로 파생하므로(resolve_progress), 파일만 추가하면
# 새 주차가 자동으로 인식된다.
CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"


def _load_content_by_week() -> dict[int, dict]:
    by_week: dict[int, dict] = {}
    for path in sorted(CONTENT_DIR.glob("questions-week*.json")):
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        week = data["week"]
        if week in by_week:
            raise RuntimeError(f"주차 {week} 콘텐츠 파일이 중복됩니다: {path}")
        by_week[week] = data
    if not by_week:
        raise RuntimeError("content/questions-week*.json 파일을 찾지 못했습니다")
    return by_week


CONTENT_BY_WEEK = _load_content_by_week()
MAX_WEEK = max(CONTENT_BY_WEEK)


def content_for_week(week: int) -> dict:
    """요청한 주차 콘텐츠. 아직 파일이 없는 주차(커리큘럼이 더 준비되기 전)는
    마지막 주차 콘텐츠를 반복한다 — 조용히 죽지 않게 하기 위한 의도된 fallback."""
    return CONTENT_BY_WEEK.get(week, CONTENT_BY_WEEK[MAX_WEEK])

# Mon=0 … Sun=6 (date.weekday()와 정렬)
WEEKDAYS = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

# ── 유일하게 남은 메모리 상태 (4-a 결정: 세션 내 임시값이라 DB 불필요) ──────
# 서버 재시작하면 초기화된다 — 의도된 동작이다 (진행 중이던 문항 재시도 상태일
# 뿐, 사용자 식별 데이터가 아니다). consecutive_correct/wrong은 이제 DB
# session_progress로 옮겼다 (Phase 4-c-3, 아래).
_attempts: dict[tuple[int, int], int] = {}  # (session_id, question_id) -> 시도 횟수


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


# ── 판정 (api-spec §4) ────────────────────────────────────────────
def find_question(question_id: int, content: dict) -> dict | None:
    """content(오늘 세션이 속한 주차 콘텐츠 하나)에서 question_id로 문항 정의를 찾는다.
    호출부(submit_answer)가 항상 resolve_progress로 같은 주차를 다시 계산해 넘기므로
    오늘 세션에 없는 question_id가 들어올 일은 없다."""
    for w in content["common"]["warmup"].values():
        # "_note" 같은 설명용 문자열 키가 섞여 있어 dict인 것만 본다.
        if isinstance(w, dict) and w.get("id") == question_id:
            return w
    for day in content["days"]:
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


def _time_of_day(hour: int) -> str:
    if 5 <= hour < 11:
        return "아침"
    if 11 <= hour < 17:
        return "낮"
    if 17 <= hour < 21:
        return "저녁"
    return "밤"


def compute_dynamic_answer(rule: str, today: date) -> str:
    """dynamic 문항의 answer_rule대로 오늘 날짜(시각) 기준 정답을 서버가 계산한다
    (content/questions-week*.json에 쓰인 answer_rule 어휘 전부 지원)."""
    if rule == "time_of_day":
        return _time_of_day(datetime.now().hour)
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


def _weekday_neighbor_choices(idx: int) -> list[str]:
    """idx(정답 요일의 WEEKDAYS 인덱스) 기준으로 정답+인접 요일 3개를 만든다
    (weekday_4 규칙)."""
    return [WEEKDAYS[idx], *(WEEKDAYS[(idx + off) % 7] for off in (-1, 1, 2))]


def _date_neighbor_choices(today: date) -> list[str]:
    """date_4 규칙: 정답(오늘) + 앞뒤 며칠 3개. 월·연도 경계는 timedelta가 처리한다."""
    dates = [today, *(today + timedelta(days=o) for o in (-1, 1, 2))]
    return [f"{d.month}월 {d.day}일" for d in dates]


def _month_neighbor_choices(month: int) -> list[str]:
    """month_4 규칙: 정답 + 인접 월 3개."""
    idx0 = month - 1
    neighbors = [(idx0 + off) % 12 + 1 for off in (-1, 1, 2)]
    return [f"{month}월", *(f"{m}월" for m in neighbors)]


def _year_neighbor_choices(year: int) -> list[str]:
    """year_4 규칙: 정답 + 앞뒤 연도 3개."""
    return [f"{year}년", *(f"{year + off}년" for off in (-1, 1, 2))]


def build_dynamic_main_choices(question: dict, today: date) -> list[str]:
    """main 단계 dynamic 문항(파일에 고정 choices가 없고 choices_rule만 있는 경우)의
    보기 목록을 만든다. compute_dynamic_answer가 계산하는 정답과 항상 같은 어휘를
    쓰므로 정답이 이 목록 밖에 있을 일이 없다. 호출부에서 deterministic_shuffle로
    섞는다 (여기서는 섞지 않은 원본 순서로 반환)."""
    rule = question["answer_rule"]
    if rule == "season_temp":
        return ["더운 계절", "추운 계절"]
    if rule == "time_of_day":
        return ["아침", "낮", "저녁", "밤"]
    if rule.startswith("weekday_offset:"):
        offset = int(rule.split(":", 1)[1])
        return _weekday_neighbor_choices((today.weekday() + offset) % 7)
    if rule == "month":
        return _month_neighbor_choices(today.month)
    if rule == "year":
        return _year_neighbor_choices(today.year)
    raise ApiError(500, "INTERNAL_ERROR", "잠깐 문제가 생겼어요. 다시 해보세요")


def build_dynamic_warmup_choices(rule: str, today: date) -> list[str]:
    """warmup 단계는 레벨별로 answer_rule이 다르다(1=weekday_type 2택, 2=weekday
    4택, 3=month_day 4택). 예전엔 레벨이 2로 고정돼 있어서(decisions.md 2026-07-19)
    weekday 전용 함수 하나로 충분했는데, 실제 레벨 조회로 바뀐 뒤에도 이 부분만
    안 고쳐져 레벨 1·3에서 프롬프트와 안 맞는 보기(정답이 보기에 없음)가 나가는
    버그가 있었다 — 이번에 발견해서 규칙별로 분기하도록 고친다."""
    if rule == "weekday_type":
        return ["평일", "주말"]
    if rule == "weekday":
        return _weekday_neighbor_choices(today.weekday())
    if rule == "month_day":
        return _date_neighbor_choices(today)
    raise ApiError(500, "INTERNAL_ERROR", "잠깐 문제가 생겼어요. 다시 해보세요")


def select_main_question(day: dict, level: int, today: date) -> dict:
    """day['main'][level] 을 고르되, day2 level1(계절 이분법 season_temp)은 봄·가을엔
    성립하지 않아 예비 문항(f"{level}_alt")으로 대체한다 (파일 _note, PRD 설계 그대로).
    다른 day/level은 그냥 원래 항목을 쓴다."""
    key = str(level)
    item = day["main"][key]
    if item.get("answer_type") == "dynamic" and item.get("answer_rule") == "season_temp":
        season = _season_of(today.month)
        alt_key = f"{key}_alt"
        if season in ("봄", "가을") and alt_key in day["main"]:
            return day["main"][alt_key]
    return item


def judge(question: dict, response: str, today: date) -> bool:
    """정답 판정은 서버에서만 (api-spec §0.5). 정답 값 자체는 반환하지 않는다."""
    if question["answer_type"] == "static":
        return response == question["answer"]
    return response == compute_dynamic_answer(question["answer_rule"], today)


# ── 연속 성공/실패 (session_progress, Phase 4-c-3) ────────────────
def get_progress(user_id: str) -> tuple[int, int]:
    """(consecutive_correct, consecutive_wrong). 행이 없으면 (0, 0).

    ★ user_id 기준 한 행만 유지한다(session_id로 나누지 않는다). judged 문항이
    하루(세션) 안에 warmup·main 2개뿐이라, 3연속 성공은 여러 세션(날짜)에 걸쳐야
    실제로 채워진다 — 세션마다 새로 세면 이 규칙(PRD §3.3)이 절대 트리거되지
    않는다. session_id 컬럼은 "가장 최근에 갱신한 세션"을 남기는 참고용이다."""
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT consecutive_correct, consecutive_wrong FROM session_progress WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return 0, 0
    return row["consecutive_correct"], row["consecutive_wrong"]


def save_progress(
    user_id: str, session_id: int, consecutive_correct: int, consecutive_wrong: int
) -> None:
    """user_id당 한 행을 유지하는 수동 upsert (파라미터화 쿼리만 사용)."""
    with db.get_connection() as conn:
        existing = conn.execute(
            "SELECT 1 FROM session_progress WHERE user_id = ?", (user_id,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE session_progress "
                "SET session_id = ?, consecutive_correct = ?, consecutive_wrong = ? "
                "WHERE user_id = ?",
                (str(session_id), consecutive_correct, consecutive_wrong, user_id),
            )
        else:
            conn.execute(
                "INSERT INTO session_progress "
                "(session_id, user_id, consecutive_correct, consecutive_wrong) "
                "VALUES (?, ?, ?, ?)",
                (str(session_id), user_id, consecutive_correct, consecutive_wrong),
            )


def _record_outcome(user_id: str, session_id: int, *, success: bool) -> None:
    """문항의 '최종' 결과(재시도 중이 아닌)만 연속 성공/실패에 반영한다."""
    correct, wrong = get_progress(user_id)
    if success:
        correct += 1
        wrong = 0
    else:
        wrong += 1
        correct = 0
    save_progress(user_id, session_id, correct, wrong)


# ── 도장판·연속 참여일 (daily_completions, api-spec §5·§6) ─────────
def get_completed_dates(user_id: str) -> set[str]:
    """이 사용자가 완료한 모든 날짜(YYYY-MM-DD)를 daily_completions에서 조회."""
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT date FROM daily_completions WHERE user_id = ?", (user_id,)
        ).fetchall()
    return {row["date"] for row in rows}


def resolve_progress(user_id: str) -> tuple[int, int, dict]:
    """이 유저가 오늘 봐야 할 (week_number, day_index, content) 를 파생한다.

    daily_completions에 쌓인 '완료한 총 일수'(N)만으로 계산한다 — 별도 컬럼에
    저장하지 않는다. users.week 컬럼(db-schema.md)이 있지만 이 계산에는 쓰지
    않는다: streak_days를 daily_completions에서 매번 세는 것과 같은 이유로,
    저장된 카운터는 갱신을 빠뜨리면 어긋나지만 파생값은 항상 맞는다.

    N=0(첫 세션)이면 week1의 day1. 5일 완료할 때마다 다음 주차로 넘어간다.
    아직 콘텐츠 파일이 없는 주차는 content_for_week가 마지막 주차로 clamp한다."""
    total_completed = len(get_completed_dates(user_id))
    week_number = total_completed // 5 + 1
    day_index = total_completed % 5
    return week_number, day_index, content_for_week(week_number)


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
    # §3. 완료 개수로 파생한 오늘의 day/week 문항을 파일에서 읽어 5단계 구성.
    # answer 절대 미포함.
    today = date.today()
    session_id = derive_session_id(user_id, today)
    week_number, day_index, content = resolve_progress(user_id)
    day = content["days"][day_index]
    common = content["common"]
    level = get_user_level(user_id)

    # mood: 판정 없음 + 정서 척도(좋아요→별로예요)라 순서 유지 (셔플 안 함)
    mood = {
        "prompt": common["mood"]["prompt"],
        "choices": list(common["mood"]["choices"]),
    }

    # warmup: 레벨별 answer_rule에 맞는 보기를 만들어 결정적 셔플.
    w = common["warmup"][str(level)]
    warmup_choices = build_dynamic_warmup_choices(w["answer_rule"], today)
    warmup = {
        "question_id": w["id"],
        "prompt": w["prompt"],
        "choices": deterministic_shuffle(warmup_choices, session_id, w["id"]),
    }

    # main: static이면 파일 choices 그대로, dynamic이면 규칙대로 생성. 둘 다 결정적 셔플.
    m = select_main_question(day, level, today)
    if "choices" in m:
        main_choices = m["choices"]
    else:
        main_choices = build_dynamic_main_choices(m, today)
    main = {
        "question_id": m["id"],
        "prompt": m["prompt"],
        "choices": deterministic_shuffle(main_choices, session_id, m["id"]),
    }

    # recall: 판정 없는 회상 질문 (question_id 없음)
    recall = {"prompt": day["recall"]["prompt"]}
    mission = {"text": day["mission"]["text"]}

    return {
        "session_id": session_id,
        "date": today.isoformat(),
        "week": content["week"],
        "domain": content["domain"],
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
                # 지금까지(1~2주차)는 도메인 전환이 없어 1주차 파일 기준으로 고정.
                # 3주차 이후 다른 도메인 콘텐츠가 생기면 날짜별 실제 도메인을
                # 추적하도록 재검토 필요 (지금은 과잉설계 방지 차원에서 보류).
                "domain": CONTENT_BY_WEEK[1]["domain"] if done else None,
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
    # 오늘 세션과 동일한 계산식(resolve_progress)으로 이 유저의 주차 콘텐츠를 다시
    # 구해서 그 안에서만 문항을 찾는다 — /session/today가 내준 문항과 항상 같은
    # 주차를 보게 되므로 어긋날 일이 없다.
    _week_number, _day_index, content = resolve_progress(user_id)
    question = find_question(body.question_id, content)
    if question is None:
        raise ApiError(404, "QUESTION_NOT_FOUND", "문항을 찾지 못했어요")

    key = (session_id, body.question_id)
    attempt = _attempts.get(key, 0) + 1
    _attempts[key] = attempt

    correct = judge(question, body.response, date.today())
    messages = content["common"]["messages"]

    if correct:
        # 1차든 2차 시도든, 맞으면 성공 — 재시도 규칙과 무관하게 바로 통과.
        _record_outcome(user_id, session_id, success=True)
        return {
            "correct": True,
            "attempts": attempt,
            "message": messages["correct"],
            "next_action": "proceed",
        }

    if attempt >= 2:
        # 2차 오답 → 최종 실패. 정답은 끝까지 알려주지 않는다.
        _record_outcome(user_id, session_id, success=False)
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
    # 오늘 완료를 기록하기 '전' 상태로 오늘 세션의 day/week를 파생한다 — 완료를
    # 먼저 기록해버리면 N이 1 늘어나 다음 날 것을 계산하게 되므로 순서가 중요하다
    # (기존 버그: 미션이 항상 day1 것만 나왔다 — CONTENT["days"][0] 하드코딩 때문).
    _week_number, day_index, content = resolve_progress(user_id)
    mission = content["days"][day_index]["mission"]["text"]

    # 오늘 완료를 daily_completions에 기록 (같은 날 재완료는 409 ALREADY_COMPLETED).
    record_completion(user_id, today)

    # §5. 3연속 성공 → 상승 / 2연속 실패 → 하강 (PRD §3.3). 여기서만 난이도가 바뀐다.
    # consecutive_correct/wrong·level 전부 DB가 유일한 출처 (Phase 4-c-1/2/3).
    consecutive_correct, consecutive_wrong = get_progress(user_id)
    level = get_user_level(user_id)
    next_level = level

    if consecutive_correct >= 3:
        next_level = min(level + 1, 3)
        consecutive_correct = 0
    elif consecutive_wrong >= 2:
        next_level = max(level - 1, 1)
        consecutive_wrong = 0

    level_changed = next_level != level
    if level_changed:
        update_user_level(user_id, next_level)
        save_progress(user_id, session_id, consecutive_correct, consecutive_wrong)

    # streak_days: daily_completions에서 실제 집계 (Phase 4-c-2, 고정 샘플 제거).
    completed_dates = get_completed_dates(user_id)
    streak_days = compute_streak_days(completed_dates, today)
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

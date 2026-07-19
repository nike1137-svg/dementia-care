"""dementia-care API (FastAPI).

api-spec §0.1: 브라우저는 /api/py/* 를 호출하고, Next.js rewrites가 '/api/py'
접두어를 떼어 이 서버의 /* 로 중계한다. 따라서 이 서버는 접두어 없이 서빙한다.

Phase 2-b-1: 판정 없는 엔드포인트 3개 (users, session/today, history).
             로직은 실제로 짜고 문항 데이터는 content/questions-week1.json 에서 읽는다.
             DB는 없다 (Phase 4에서 붙음). answer(정답)·점수는 절대 응답에 넣지 않는다.

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

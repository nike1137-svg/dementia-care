"""dementia-care API (FastAPI).

api-spec §0.1: 브라우저는 /api/py/* 를 호출하고, Next.js rewrites가 '/api/py'
접두어를 떼어 이 서버의 /* 로 중계한다. 따라서 이 서버는 접두어 없이 /health 로
서빙한다. (브라우저용 /api/py/health → web 프록시 → 이 서버 /health)

로컬 직접 확인: uvicorn index:app --host 127.0.0.1 --port 8000
              curl http://127.0.0.1:8000/health
"""

from fastapi import FastAPI

app = FastAPI(title="dementia-care API")


@app.get("/health")
def health():
    # api-spec §7. Phase 2-a는 DB 미연결 — db는 하드코딩 "ok" (Phase 4에서 실제 점검).
    return {"status": "ok", "db": "ok"}

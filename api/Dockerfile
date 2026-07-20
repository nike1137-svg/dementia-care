# api/Dockerfile — FastAPI 백엔드
#
# ★ 빌드 컨텍스트는 저장소 루트(.)여야 한다, api/ 단독이 아니다.
#   api/index.py가 content/questions-week1.json을 "../content"(parent.parent)
#   상대경로로 읽는다 — content/가 api/의 형제 디렉터리로 이미지 안에도 그대로
#   있어야 한다. docker-compose.yml(5-b)에서 반드시:
#     build: { context: ., dockerfile: api/Dockerfile }
#   로 지정한다.

FROM python:3.12-slim

WORKDIR /app

# 레이어 캐싱: requirements 먼저 복사·설치 → 코드는 그 다음 (코드가 더 자주 바뀐다)
COPY api/requirements.txt ./api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

# content/는 api/의 형제 디렉터리로 그대로 유지 (위 이유). api/data/*.db는
# .dockerignore가 걸러낸다 — DB는 named volume으로 붙는 자리라 이미지에 안 넣는다.
COPY content/ ./content/
COPY api/ ./api/

# non-root 실행 (threat-model §6 #5). 호스트 UID:GID 1000:1000과 맞춘다
# (threat-model §8-4에서 확인된 값) — named volume 권한 문제를 피하기 위함이다.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin app \
    && chown -R 1000:1000 /app

USER 1000:1000

WORKDIR /app/api
EXPOSE 8000

# 컨테이너 내부 0.0.0.0 바인딩. ports: 매핑이 0개(threat-model §6 #3)면
# 호스트에는 열리지 않는다 — web 컨테이너만 도커 네트워크로 도달 가능.
CMD ["uvicorn", "index:app", "--host", "0.0.0.0", "--port", "8000"]

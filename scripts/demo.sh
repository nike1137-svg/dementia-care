#!/usr/bin/env bash
# 데모용 로컬 서버 — 화면으로 아무 주차나 확인하기 위한 개발 도구.
#
# 도커를 쓰지 않는다(= sudo 불필요). 운영 컨테이너·운영 DB와 완전히 별개다:
#   - DB      : api/data/demo.db  (운영 DB는 도커 named volume 안, 접근하지 않는다)
#   - 포트    : 3000(web) / 8000(api) — 운영 컨테이너는 ports 매핑이 0개라 충돌 없음
#   - 터널    : 절대 띄우지 않는다. 외부에 노출되지 않는 localhost 전용이다
#
# 사용법:
#   ./scripts/demo.sh              # 서버 두 개 기동 (Ctrl+C 로 함께 종료)
#   그 다음 다른 터미널에서:
#   python3 scripts/demo_jump.py --week 4 --day 2 --level 3

set -euo pipefail
cd "$(dirname "$0")/.."

DEMO_DB="${DEMENTIA_DB_PATH:-$PWD/api/data/demo.db}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"
VENV_PY="$PWD/api/.venv/bin/python"

[ -x "$VENV_PY" ] || { echo "파이썬 가상환경이 없습니다: $VENV_PY"; exit 1; }
[ -d node_modules ] || { echo "node_modules 가 없습니다. 먼저 'npm install' 을 실행하세요."; exit 1; }

for port in "$API_PORT" "$WEB_PORT"; do
  if ss -ltn 2>/dev/null | grep -q ":${port}\b"; then
    echo "포트 ${port} 가 이미 사용 중입니다. 기존 데모 서버를 끄고 다시 실행하세요."
    exit 1
  fi
done

mkdir -p "$(dirname "$DEMO_DB")"
export DEMENTIA_DB_PATH="$DEMO_DB"
export BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:${API_PORT}}"

echo "DB      : $DEMO_DB   (운영 DB 아님)"
echo "백엔드  : http://127.0.0.1:${API_PORT}"
echo "화면    : http://localhost:${WEB_PORT}"
echo

cleanup() {
  echo
  echo "종료 중…"
  [ -n "${API_PID:-}" ] && kill "$API_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

( cd api && exec "$VENV_PY" -m uvicorn index:app --host 127.0.0.1 --port "$API_PORT" ) &
API_PID=$!

for _ in $(seq 1 40); do
  curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1 && break
  sleep 0.3
done
curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1 \
  || { echo "백엔드가 뜨지 않았습니다."; exit 1; }
echo "백엔드 준비 완료. 화면 서버를 띄웁니다 (첫 기동은 조금 걸립니다)…"
echo

exec npm run dev -- --port "$WEB_PORT"

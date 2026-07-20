# Dockerfile — Next.js 프런트(web).
#
# ★ 이 프로젝트엔 web/ 폴더가 따로 없다. Next.js 파일이 저장소 루트에 그대로
#   있어서(app/, public/, package.json 등) 이 Dockerfile도 루트에 둔다.
#   docker-compose.yml(5-b)에서: build: { context: ., dockerfile: Dockerfile }
#
# 멀티스테이지: 빌드 스테이지(전체 의존성 + next build)와 실행 스테이지
# (프로덕션 의존성 + 빌드 산출물만)를 분리해 최종 이미지를 가볍게 한다.
# next.config.ts의 output 설정은 건드리지 않았다(Phase 5-a는 파일 작성만) —
# standalone output으로 바꾸면 이미지가 더 작아지지만 그건 별도 결정 사항이다.

FROM node:22-slim AS base
WORKDIR /app

# ---- deps: 프로덕션 의존성만 (런타임 이미지에 들어갈 것) ----
FROM base AS deps
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# ---- builder: 전체 의존성(devDependencies 포함) + 빌드 ----
FROM base AS builder
# next.config.ts의 rewrites()는 next build 시점에 호출돼 라우팅 매니페스트로
# 굽힌다(Phase 3-a fail-loud 설계 — BACKEND_URL 없으면 에러). 비밀값이 아니라
# 컨테이너 내부 주소(http://api:8000)일 뿐이라 빌드 인자로 넣어도 안전하다.
# 값은 docker-compose.yml의 web.build.args가 전달한다 (fail-loud 검사는 유지).
ARG BACKEND_URL
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---- runner: 실행 전용. 프로덕션 의존성 + 빌드 산출물만 담는다 ----
FROM base AS runner
ENV NODE_ENV=production

# non-root 실행 (threat-model §6 #5). node:22-slim(공식 이미지)엔 이미
# uid:gid 1000:1000인 `node` 사용자가 있다(호스트 UID:GID와 동일, threat-model
# §8-4) — 새로 만들지 않고 그대로 쓴다. groupadd/useradd를 다시 시도하면
# gid/uid 1000이 이미 있어 "already exists"로 빌드가 실패한다(exit 4).
# 홈 디렉터리도 base 이미지가 만들 때 이미 /home/node로 준비돼 있다.

COPY --from=deps /app/node_modules ./node_modules
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.ts ./next.config.ts

RUN chown -R 1000:1000 /app
USER 1000:1000

EXPOSE 3000
ENV PORT=3000

# 컨테이너 내부 0.0.0.0 바인딩. BACKEND_URL은 이미지에 안 넣는다 —
# compose(5-b)가 환경변수로 주입한다 (.env.local은 로컬 전용, 이미지에 안 들어간다).
CMD ["./node_modules/.bin/next", "start", "-H", "0.0.0.0", "-p", "3000"]

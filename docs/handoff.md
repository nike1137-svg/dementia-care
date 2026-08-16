# 인계 메모 — 2026-08-16 (리눅스 데스크탑 → 윈도우 노트북 WSL)

개발 환경을 리눅스 데스크탑에서 **윈도우 노트북 WSL**로 옮기며 남기는 메모다.

**이 파일이 왜 필요한가:** 클로드코드 세션 기록은 기기 로컬(`~/.claude/projects/`)에만
저장된다. 계정이 같아도 노트북에서는 데스크탑의 대화를 볼 수 없다. **넘겨야 할 정보는
전부 이 파일에 적는다.** 노트북에서 새 세션을 시작하면 이 파일부터 읽게 하라.

역할 분담: **데스크탑 = 운영 서버**, **노트북 WSL = 개발 환경**, GitHub이 둘 사이 통로.

---

## 1. 지금 상태 (2026-08-16 실측 확인)

| 구분 | 상태 |
|---|---|
| 앱 (Phase 0~7) | **전부 완료** — 프런트·FastAPI·SQLite·Docker·터널·Access·README |
| 콘텐츠 | **12주 중 1주차만** — `content/questions-week1.json` (지남력, 5일치) |
| 서비스 | 데스크탑에서 가동 중. `care.dodami-ai.com` (Cloudflare Access 뒤) |
| 컨테이너 | `web`·`api`·`cloudflared` 3개 모두 Up, 재시작 정책 `unless-stopped` |
| 미검증 코드 | **없음.** 마지막 수정까지 실제 서비스에서 동작 확인 완료 |

**서비스와 저장소가 일치한다.** 노트북에서 `git clone` 하면 지금 돌고 있는 것과 같은
코드를 받는다. (2026-08-16 web 이미지 재빌드·배포 완료 기준)

## 2. 직전에 무슨 일이 있었나 — 반드시 읽을 것

2026-07-23 세션에서 "오늘 마치기" 재시도 시 겁나는 에러 화면이 뜨는 문제를 고쳤으나,
**실제 동작 검증 직전에 세션이 중단**되어 커밋되지 않은 채 3주간 방치됐다. 같은 시기
터널 컨테이너도 멈춰 외부 접속이 끊겨 있었다. 둘 다 2026-08-16에 해소했다.

- 원인·경과 상세: `docs/decisions.md` 2026-08-16 항목
- **교훈: 검증 미완 상태로 작업이 끊기면 커밋이 없어 재개 지점을 잃는다.**
  중단할 때는 미완 상태를 커밋이나 문서로 남길 것.

## 3. git에 없는 것 — 노트북에서 따로 챙긴다

| 항목 | 왜 없나 | 노트북에서 할 일 |
|---|---|---|
| `.env` (`TUNNEL_TOKEN`) | `.gitignore` 처리 (비밀값) | 가짜 값으로 채운다 (§4-2) |
| SQLite 데이터 | 도커 named volume에 있음 | 노트북은 빈 DB로 시작. 정상이다 |
| `docker-compose.override.yml` | `.gitignore` 처리 | 포트 열 때 만든다 (§4-4) |
| 클로드코드 세션 기록 | 기기 로컬 저장 | 이 파일이 대체물이다 |

## 4. 노트북 WSL 최초 셋업

**(1) 저장소 받기.** remote가 SSH(`git@github.com:nike1137-svg/dementia-care.git`)다.
노트북에 SSH 키가 없으면 **노트북에서 새로 만들어 GitHub에 등록**한다.
데스크탑의 개인키를 복사하지 마라.

```bash
git clone git@github.com:nike1137-svg/dementia-care.git
```

**(2) 가짜 `.env`.** compose가 `${TUNNEL_TOKEN:?...}`(docker-compose.yml 85행)를
파일 전체에서 해석하므로, 터널을 안 띄워도 값이 없으면 멈출 가능성이 있다
(*미확인 — 노트북에서 실제로 확인할 것*). **진짜 토큰을 노트북에 복사하지 마라.**

```bash
umask 077 && echo 'TUNNEL_TOKEN=dummy-not-a-real-token' > .env
```

**(3) 🚫 노트북에서 cloudflared를 절대 실행하지 마라.**
같은 토큰으로 두 기기에서 터널을 켜면 Cloudflare가 트래픽을 양쪽으로 분산시켜
접속할 때마다 다른 기기로 가는 이상 동작이 생긴다. `--profile tunnel` 을 쓰지 않으면
기본 `up` 에서 제외되므로, 그냥 쓰지 않으면 된다.

**(4) 화면을 보려면 포트를 열어야 한다.** 운영용 compose는 `ports:` 매핑이 0개다
(보안 설계 — 건드리지 마라). 노트북에서만 `docker-compose.override.yml` 로 덮어쓴다.
이 파일은 이미 `.gitignore` 에 있어 커밋되지 않는다.

## 5. 노트북 작업분을 서버에 반영하기

코드는 **이미지 안에 구워져** 있어 `git pull` 만으로는 안 바뀐다. 재빌드가 필요하다.

```bash
cd ~/projects/dementia-care && git pull && sudo docker compose build web && sudo docker compose up -d --no-deps web
```

`cloudflared` 는 profile 밖이라 이 명령에 영향받지 않고 계속 떠 있는다.
데스크탑에서 `sudo` 는 사람이 직접 입력해야 한다 (클로드코드 세션엔 TTY가 없다).

## 6. 다음 할 일

1. **web Dockerfile `RUN chown -R 1000:1000 /app` 개선** — 빌드 646초 중 **523초**를
   이 한 줄이 쓴다. `COPY --chown=1000:1000` 으로 옮기면 제거 가능. 노트북에서 빌드를
   자주 돌릴 거라면 이걸 먼저 하는 게 이득이다. 기능 영향 없음.
2. **2주차 콘텐츠** — `content/questions-week2.json`.
   `questions-week1.json` 과 같은 형식(`week`·`domain`·`levels` 1~3·`days` 5개)으로
   파일만 추가하면 된다. 앱 코드는 건드릴 필요 없다.
3. PRD §3.2 커리큘럼: 6영역 × 2주 = 1사이클, 13주차부터 난이도 올려 재순환.

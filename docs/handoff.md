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
| 콘텐츠 | **12주 중 2주차까지** — `content/questions-week1.json`·`questions-week2.json` (지남력, 각 5일치) |
| 서비스 | 데스크탑에서 가동 중. `care.dodami-ai.com` (Cloudflare Access 뒤) |
| 컨테이너 | `web`·`api`·`cloudflared` 3개 모두 Up, 재시작 정책 `unless-stopped` |
| 미검증 코드 | **있음.** day/week 순환 로직(`api/index.py`, 2026-08-16 노트북 작업)이 로컬(WSL)에서만 검증됐고 **데스크탑 운영 컨테이너엔 아직 배포 안 됨** — 배포 전 운영 DB 완료 기록 확인 필요(§6-2) |

**서비스와 저장소가 어긋나 있다 (이번 항목에 한해).** 노트북에서 `git clone` 하면
day/week 순환 로직·week2 콘텐츠가 포함된 최신 코드를 받지만, 데스크탑에서 지금
가동 중인 컨테이너는 아직 이전 이미지(day1 고정)로 돌고 있다. 배포하려면 §5의
재빌드 절차를 데스크탑에서 실행해야 한다.

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
2. **2주차 콘텐츠 — 2026-08-16 완료.** `content/questions-week2.json` 추가.
   ~~이 항목은 원래 "파일만 추가하면 된다, 앱 코드는 안 건드려도 된다"고 적혀
   있었는데 틀린 서술이었다.~~ 실제로 열어보니 `api/index.py`가 `content/questions-week1.json`
   파일명을 하드코딩하고, `/session/today`·`/complete`가 항상 `CONTENT["days"][0]`
   (1일차)만 내보내고 있었다 — 몇 주가 지나도 day1만 반복 재생되는 상태였다. 그래서
   이번에 `api/index.py`도 함께 고쳤다:
   - `daily_completions` 완료 개수(N)로 `week`/`day`를 파생(`week=N//5+1`,
     `day_index=N%5`) — DB 스키마 변경 없음, `content/questions-week*.json`을 전부
     스캔해 없는 주차는 마지막 주차로 자동 clamp (`docs/api-spec.md` §3.1 참조).
   - 덤으로 발견한 버그 2개도 같이 고침: ① `complete`의 미션 문구가 항상 day1
     것만 나오던 버그, ② warmup 단계가 레벨과 무관하게 항상 "요일 4택" 보기만
     만들어서 레벨 1(평일/주말 2택)·레벨 3(날짜 4택) 사용자는 **정답이 보기에
     없어 워밍업을 통과할 수 없던** 버그. 후자는 day/week 순환과 무관하게
     레벨 1(신규 유저 기본값)이면 항상 겪는 문제라 심각도가 높았다.
   - 로컬(WSL, uvicorn+next dev 프록시 경유)에서 day1~5 순환, week1→week2 전환,
     미션 문구, 워밍업 보기 전부 curl로 실측 검증 완료. 운영 컨테이너(데스크탑)
     배포는 아직 안 함 — 배포 전 운영 DB에 기존 완료 기록이 있는지 확인 필요
     (있으면 유저가 콘텐츠 진행 위치가 한 번 점프하는 정도의 UX 변화, 데이터
     손실은 아님. 상세: `docs/decisions.md` 2026-08-16 항목).
3. PRD §3.2 커리큘럼: 6영역 × 2주 = 1사이클, 13주차부터 난이도 올려 재순환.

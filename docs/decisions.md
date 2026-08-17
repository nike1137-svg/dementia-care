# 결정 기록 (Decisions)

## 2026-07-18 — postcss/next 취약점(GHSA-qx2v-qp2m-jg93) 미조치

- **무엇**: `next@16.2.10`이 물고 오는 간접 의존성 `postcss@8.4.31`의 moderate XSS 경고 2건.
- **왜 안 고치나**: postcss는 **빌드 타임 전용** 도구이고, 우리는 사용자 입력 CSS를 postcss로 처리하는 경로가 없다. → **우리 공격 표면에 닿지 않는다.** `npm audit fix --force`는 next를 9.3.3으로 다운그레이드해 프로젝트를 파괴한다.
- **재검토 시점**: Next.js가 상위 릴리스에서 postcss를 올릴 때 따라간다. `npm audit fix`는 마커스님 승인 없이 실행 금지.

## 2026-07-19 — Phase 2-b: /session의 level을 2로 임시 고정

POST /users는 §2대로 level 1을 반환하지만, /session/today는 level 2로 세션을 구성한다. DB가 없어 사용자별 레벨을 저장·조회할 수 없기 때문. 프런트 목데이터(day1·level2)와 맞춰 Phase 3 교체를 매끄럽게 하려는 의도. Phase 4에서 users 테이블의 실제 level로 대체 예정. 이 시점까지 두 값 불일치는 버그가 아니라 임시 상태다.

**[2026-07-20] Phase 4-c-1에서 해소됨** — users.level 실제 조회로 대체.

## 2026-07-20 — Phase 4-a: SQLite 스키마 확정

users·daily_completions·session_progress 3테이블. 도장판은 daily_completions를 날짜로 세어 계산(A 방식). attempts는 메모리 유지, 문항은 파일 유지. 상세 근거는 `docs/db-schema.md` 참조.

## 2026-07-20 — Phase 4-c-2에서 해소됨 — history/complete의 고정 샘플

/history의 도장판과 /complete의 streak_days는 Phase 2-b-1·2-b-2에서 DB가 없어 고정 샘플(`pattern`/`PAST_DAYS_SAMPLE`)로 형태만 흉내 냈다. 이 임시조치는 코드 주석에만 적혀 있었고 이 문서엔 정식 항목이 없었다 — 지금 처음이자 마지막으로 기록한다. `daily_completions` 테이블에서 실제 집계하도록 대체 완료(A 방식, `docs/db-schema.md` §2.1). 고정 샘플 코드(`PAST_DAYS_SAMPLE`)는 삭제했다.

## 2026-07-20 — Phase 4-c-3 완료 — session_progress로 연속 성공/실패 이관. 메모리 상태는 attempts(세션 내 임시값, 의도적 유지)만 남고 영구 데이터는 전부 DB로. Phase 4 종료.

## 2026-07-20 — Phase 5-c 완료 — docker compose로 3서비스 기동 실측 검증.

확인: 컨테이너 안정 기동, 호스트 포트 매핑 0개(ss로 확인), web↔api 컨테이너 통신, SQLite 볼륨 쓰기, read_only+tmpfs 정상. web Dockerfile 빌드오류 2건(1000:1000 사용자 중복, BACKEND_URL 빌드인자) 수정 후 통과.

## 2026-07-20 — Phase 6 완료 — Cloudflare Tunnel + Access 적용.

터널(dementia-care)로 care 서브도메인을 web:3000에 라우팅, cloudflared 컨테이너가 터널에 연결(4개 커넥션). Access로 지정 이메일 OTP 인증자만 접근 허용 실측 확인. §8-1(Cloudflare Access 적용 여부) 해소: 적용함.

## 2026-08-16 — 터널 3주 중단 복구 + 409 ALREADY_COMPLETED 처리 완결

**터널 중단.** cloudflared 컨테이너가 2026-07-23경 정상 종료(exit 0)된 뒤 3주간 외부
접속이 끊겨 있었다. 원인은 compose의 `restart: "no"` — Phase 6 전 자리표시자 시절
값이 토큰 적용 후에도 남아 있어, 재부팅 때 web·api만 살아나고 터널은 따라오지
못했다. `unless-stopped`로 바꿔 해소(커밋 ead0312). `profiles: ["tunnel"]`은 유지 —
재시작 정책은 컨테이너 단위라 최초 1회만 profile로 띄우면 이후는 자동 복구된다.

**409 처리.** 2026-07-23 세션에서 "오늘 마치기" 재시도 시 겁나는 에러 화면이 뜨는
문제를 잡아 수정했으나, **실제 동작 검증 직전에 세션이 중단**되어 커밋되지 못한 채
3주간 방치됐다. 오늘 코드 검토·타입체크로 완결성을 확인해 커밋하고(4911896),
web 이미지를 재빌드해 배포한 뒤 실제 서비스에서 검증 완료:

- 백엔드는 처음부터 정상이었다 — 재시도 시 `POST /complete → 409 Conflict` 정상 반환
- 프런트가 그 정상 거부를 에러 화면으로 표시한 것이 문제였다
- 수정 후 실측: "오늘은 이미 잘 하셨어요! 내일 또 만나요." + 홈으로 단추 정상 표시

**교훈:** 검증 미완 상태로 세션이 끊기면 커밋도 남지 않아 재개 지점을 잃는다.
중단 시점에 미완 상태를 문서나 커밋으로 남길 것.

**미조치(별건):** web Dockerfile의 `RUN chown -R 1000:1000 /app` 이 빌드 646초 중
523초를 차지한다. `COPY --chown=` 으로 옮기면 제거 가능. 기능에는 영향 없다.

## 2026-08-16 — 2주차 콘텐츠 작업 중 day/week 순환 로직을 처음 구현, 잠재 버그 2개 함께 발견·수정

**발단.** `docs/handoff.md` §6-2는 "questions-week2.json 파일만 추가하면 된다, 앱
코드는 안 건드려도 된다"고 적혀 있었다. 실제로 `api/index.py`를 열어보니 틀렸다 —
`CONTENT_PATH`가 `content/questions-week1.json` 파일명을 하드코딩하고 있었고,
`/session/today`·`/complete`는 항상 `CONTENT["days"][0]`(1일차)만 내보내고 있었다.
즉 서비스가 몇 주째 돌아가고 있어도 항상 day1(요일) 콘텐츠만 반복 재생하는
상태였다 — day1의 문항이 우연히 전부 static/고정 보기라 이 문제가 겉으로 드러나지
않았을 뿐이다.

**조치 1 — day/week 순환을 파생값으로 구현.** `daily_completions` 완료 개수(N)로
`week = N // 5 + 1`, `day_index = N % 5`를 매 요청마다 계산(`resolve_progress`).
DB 스키마 변경 없음 — `users.week` 컬럼은 두되(무해하게 방치, `docs/db-schema.md`
갱신) 이 계산엔 안 쓴다. 콘텐츠 없는 주차는 마지막 주차로 clamp. 상세: `docs/api-spec.md` §3.1.

**조치 2 — day rotation이 실제로 켜지자마자 드러난 기존 버그, 함께 수정.**
1주차 콘텐츠만으로는 절대 드러날 수 없던(day1만 서비스했으므로) 잠재 버그 두 개를
day2 이상을 실제로 서비스해보면서 발견했다:

- **main 단계**: dynamic 문항(정답이 날짜에 따라 바뀜) 중 파일에 고정 `choices`
  배열이 없고 `choices_rule` 서술만 있는 문항 5개(계절 이분법·모레 요일·이번
  달·올해·하루의 때)에서, 보기 목록을 실제로 만드는 코드가 아예 없어 500 에러가
  났다. 신규 유저는 day2(계절 문항)에서 바로 이걸 밟는다. → `build_dynamic_main_choices`
  신설로 해결, day2 level1의 계절 예비 문항(봄·가을엔 `1_alt`로 대체) 로직도
  이번에 처음 코드로 구현했다(파일 설계 노트엔 있었지만 구현된 적 없었음).
- **warmup 단계**: 레벨과 무관하게 항상 "요일 4택" 보기만 만드는 `build_weekday_step`을
  모든 레벨에 그대로 썼다. 레벨 1(기본값, "평일/주말" 2택)·레벨 3("몇 월 며칠" 4택)
  사용자는 **프롬프트와 보기가 안 맞아 정답을 고를 수 없었다** — 실측으로 재현
  확인(레벨1 신규 유저의 세션 첫 단계에서 발생, day/week 순환과 무관). 코드 주석에
  "level 2 = dynamic 요일 문항"이라 적혀 있던 걸 보면, 레벨이 2로 고정됐던 시절
  (2026-07-19 Phase 2-b 항목 참조)에 짠 채로 남아, 나중에 실제 레벨 조회로
  바뀐 뒤에도(2026-07-20 Phase 4-c-1) 이 부분만 안 고쳐진 것으로 보인다.
  → `build_dynamic_warmup_choices`로 레벨별 규칙(weekday_type/weekday/month_day)에
  맞게 일반화, `build_weekday_step` 삭제.

**검증.** 로컬(WSL) 루트 `.venv`의 uvicorn을 재기동해 curl로 확인: day1~5 전체
순환, week1→week2 전환, `complete`의 미션 문구가 완료한 날짜와 일치(기존엔 항상
day1 미션이었던 버그도 같이 해소됨), 레벨 1/2/3 각각의 warmup·main dynamic 문항
보기가 정답을 포함해서 나오는지 전부 확인. Next.js(포트 3000) 프록시 경유로도
동일 확인. 로컬 dev DB는 검증 후 삭제해 원상 복구(0행).

**미배포.** 이 세션은 노트북(WSL) 개발 환경에서만 작업했다. 데스크탑 운영
컨테이너는 아직 이전 코드(day1 고정 버전)로 돌고 있다. 배포 전에 운영 DB
(`daily_completions`)에 기존 완료 기록이 있는지 확인 필요 — 있으면 그 유저는
배포 즉시 완료 개수만큼 앞으로 건너뛴 날짜의 콘텐츠를 보게 된다(데이터 손실은
아니고 콘텐츠 진행 위치가 한 번 점프하는 정도의 UX 변화).

**발견한 사실(미조치) — 401 NO_USER_ID를 프런트가 복구하지 못한다.**
`app/lib/userId.ts`의 `getOrCreateUserId()`는 `localStorage`에 `userId`가 이미
있으면 그 값을 그대로 쓰고, **없을 때만** `POST /users`로 새로 발급한다. 서버가
그 user_id를 모른다고 401 `NO_USER_ID`를 돌려줘도(예: 로컬 dev DB를 지우고 다시
만든 경우, 또는 운영에서 SQLite 파일이 초기화되는 경우) 이 함수는 그 사실을
알 방법이 없다 — `localStorage`엔 여전히 옛 user_id가 남아있기 때문이다.
`app/session/page.tsx`(51~52행)는 `res.ok`가 아니면 그냥
`throw new Error(session ${res.status})` 하고, `AsyncBoundary.tsx`의 에러
화면은 "다시 해보기" 버튼으로 **같은 `loadSession()`을 다시 부른다** — 즉 같은
(무효화된) user_id로 다시 요청해 또 401을 받는다. 화면이 완전히 멈추는 건
아니지만(에러 화면 자체는 뜬다), **재시도해도 근본 원인(무효 user_id)이 고쳐지지
않아 사실상 못 벗어난다.** 401을 받으면 `localStorage`를 지우고 새로 발급받는
경로가 어디에도 없다. 이번 세션에서는 고치지 않는다 — 발견만 기록.

## 2026-08-17 — day/week 순환 로직 운영 배포 + 실측 검증

노트북 WSL에서 작업한 8bfed0b(day/week 순환 + week2 콘텐츠 + 워밍업 레벨 버그)를
데스크탑 운영 컨테이너에 배포했다. 변경 범위가 `api/index.py`·`content/` 뿐이라
`api` 이미지만 재빌드(43초)하고 `--no-deps` 로 교체했다. web·cloudflared·DB 볼륨은
건드리지 않았다.

**배포 전 확인(8bfed0b의 미결정 사항 해소).** 운영 DB `daily_completions` 조회 결과
유저 2명이 각각 N=3·N=2. `week=N//5+1`, `day_index=N%5` 로 각각 week1 day4·day3 —
둘 다 week1 안이라 주차 점프가 발생하지 않는다. 지금까지 day1만 반복되던 것이
제자리를 찾아가는 것이므로 배포해도 무방하다고 판단했다.

**운영 실측 검증.** 실제 서비스(`care.dodami-ai.com`)에서 세션을 완주해 확인:

- 워밍업 통과 — 레벨 1에서 정답이 보기에 없어 진행 자체가 막히던 버그 해소 확인
- day 파생 정확 — N=3 유저에게 day4 문항이 나옴 (배포 전에는 항상 day1)
- 미션 문구 — "가족한테 안부 한마디 남겨보세요" = `questions-week1.json` day4의 미션.
  배포 전이었다면 day1의 "달력에서 오늘 날짜를 한번 찾아보세요"가 나왔을 것
- streak 2일 정상 표시

`docs/handoff.md` §1·§6-2의 "미배포·미검증" 서술을 사실에 맞게 갱신했다.


## 2026-08-17 — 3주차 콘텐츠(주의·집중) 추가 + /history domain 하드코딩 해소

**3주차 콘텐츠.** PRD §3.2대로 3~4주차는 '주의·집중' 영역이다. `content/questions-week3.json`
(5일치 × 3레벨 = 15문항)을 추가했다. 설계 판단 세 가지를 남긴다:

- **main 문항을 전부 `static`으로 짰다.** dynamic으로 하면 서버에 새 `answer_rule`·
  `choices_rule` 어휘를 추가해야 하는데, 주의·집중 과제는 날짜에 의존하지 않으므로
  이유가 없다. 덕분에 **파일 추가만으로 동작한다** (문항 관련 서버 코드 변경 0줄).
- **PRD의 대표활동 '표적 반응'(속도 과제)은 담지 않았다.** 어르신 손 떨림·오터치
  위험(PRD §4.1)이 있고 탭 전용 제약과 맞지 않는다. 4택 변별·계열 완성 과제로
  대체했다 — 주의·집중이라는 인지 목표는 같다.
- **워밍업은 그대로 지남력이다.** PRD §3.1 ②는 워밍업을 '오늘 날짜·요일'로 못박고
  있다. 주차가 바뀌어도 워밍업 규칙은 안 바뀐다는 뜻이라, week1·2의 dynamic 워밍업을
  id만 3xxx로 옮겨 그대로 썼다. `docs/api-spec.md` §3.1에 명시했다.

**/history domain 하드코딩.** `api/index.py`가 도장판의 `domain`을 `CONTENT_BY_WEEK[1]
["domain"]`(=지남력)으로 고정하고 있었다. 코드 주석이 "3주차 이후 다른 도메인
콘텐츠가 생기면 재검토 필요"라고 예고해둔 자리다 — 3주차를 넣는 순간 실제로 틀린
값이 나갔다(3주차 진행 중인 유저의 도장판이 전부 '지남력'으로 보고됨, 실측 확인).

`daily_completions`에 영역 컬럼을 추가하지 않고 파생으로 풀었다. `resolve_progress`가
'완료 개수 N'으로 주차를 정하므로, 날짜순 i번째(0-based) 완료는 그날 N=i 였다는
뜻이고 곧 `week = i//5+1` 이다. **같은 식을 쓰니 세션이 실제로 내준 영역과 어긋날 수
없다.** DB 스키마 변경 없음(`domains_by_date`).

- 사용자 영향은 없다 — 프런트(`app/history/page.tsx`)는 `domain`을 타입으로만
  선언하고 화면에 그리지 않는다. `docs/api-spec.md` §6 계약이 틀린 값을 내보내던 문제다.
- 검증: 임시 DB로 격리한 실제 앱을 uvicorn으로 띄워 HTTP로 확인. 주차 전환을 걸친
  유저(12일 완료)의 도장판에서 11~12번째 완료만 '주의·집중'으로 바뀌는 것, 미완료일
  `null` 유지, 신규 유저 전부 `null`, 오늘 세션 domain과 일치하는 것까지 확인.
- 3주차 15문항 전부 정답·오답 판정, 정답 유출 없음, 레벨별 보기 개수(2/4/4),
  N=9→10 주차 전환, 4주차 이후 clamp도 같은 방식으로 실측했다.

**미조치.** 4주차(`questions-week4.json`) 미작성 — 없으면 3주차가 반복된다(의도된
fallback). PRD §3.2대로 4주차도 주의·집중이라 반복이 치명적이진 않다.

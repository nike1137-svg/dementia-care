# dementia-care — API 명세 v1

- **작성일**: 2026-07-17
- **상태**: 마커스님 승인 대기
- **역할**: 프런트(Next.js/TypeScript)와 백엔드(FastAPI/Python)의 **계약서**

> ★ 이 문서가 기준이다. 기능이 바뀌면 **코드보다 이 문서를 먼저** 고친다.
> 프런트와 백엔드는 서로의 코드를 보지 않는다. 둘 다 이 문서만 본다.

---

## 0. 공통 규칙

### 0.1 주소 체계

| 구분 | 주소 |
|---|---|
| 브라우저가 호출하는 주소 | `https://care.dodami-ai.com/api/py/...` |
| Next.js가 중계하는 곳 | `http://api:8000/...` (도커 내부) |

`next.config.js` rewrites 설정:
```js
async rewrites() {
  return [{ source: '/api/py/:path*', destination: 'http://api:8000/:path*' }]
}
```

→ 브라우저는 **항상 같은 출처**만 부른다. CORS 없음.

### 0.2 형식
- 요청·응답 모두 `application/json`
- 인코딩 UTF-8
- 시각은 ISO 8601 (`2026-07-17T09:00:00+09:00`)
- 날짜는 `YYYY-MM-DD`

### 0.3 사용자 식별
- 로그인 없음. **익명 UUID** 만 사용
- 프런트가 `user_id` 를 브라우저에 저장하고 요청마다 헤더로 보냄

```
X-User-Id: 550e8400-e29b-41d4-a716-446655440000
```

- `X-User-Id` 가 없거나 형식이 틀리면 → `401`

### 0.4 에러 응답 (전 엔드포인트 공통)

```json
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "오늘 세션을 찾을 수 없어요"
  }
}
```

| HTTP | code | 뜻 |
|---|---|---|
| 400 | `INVALID_REQUEST` | 요청 형식 오류 |
| 401 | `NO_USER_ID` | X-User-Id 없음/형식오류 |
| 403 | `NOT_YOUR_SESSION` | 남의 세션 접근 |
| 404 | `SESSION_NOT_FOUND` | 세션 없음 |
| 404 | `QUESTION_NOT_FOUND` | 문항 없음 |
| 409 | `ALREADY_COMPLETED` | 이미 완료된 세션 |
| 500 | `INTERNAL_ERROR` | 서버 오류 |

> `message` 는 **어르신에게 그대로 보여줄 수 있는 말투**로 쓴다.
> 프런트는 `code` 로 분기하고 `message` 를 표시한다.

### 0.5 ★ 절대 규칙 (위협모델 C-7)

- **응답에 `answer`(정답)를 절대 포함하지 않는다.** 개발자도구로 다 보인다
- **정답 판정은 서버에서만** 한다
- **난이도 계산(3연속 성공/2연속 실패)은 서버에서만** 한다. 프런트가 계산해 보내면 조작 가능
- 프런트 검증은 UX용일 뿐. 공격자는 화면을 안 거치고 API를 직접 부른다

---

## 1. 엔드포인트 목록

| # | 메서드 | 경로 | 하는 일 |
|---|---|---|---|
| 1 | POST | `/api/py/users` | 익명 사용자 발급 |
| 2 | GET | `/api/py/session/today` | 오늘 세션 받기 |
| 3 | POST | `/api/py/session/{session_id}/answer` | 답 제출·판정 |
| 4 | POST | `/api/py/session/{session_id}/complete` | 세션 완료 |
| 5 | GET | `/api/py/history` | 최근 7일 도장판 |
| 6 | GET | `/api/py/health` | 컨테이너 상태 확인 |

---

## 2. `POST /api/py/users` — 익명 사용자 발급

첫 방문 시 프런트가 자동 호출. 어르신은 아무것도 안 함.

**요청**: 본문 없음. 헤더 불필요.

**응답 `201`**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "level": 1,
  "week": 1
}
```

> 프런트는 `user_id` 를 저장하고 이후 모든 요청에 `X-User-Id` 로 보낸다.

---

## 3. `GET /api/py/session/today` — 오늘 세션 받기

세션 5단계 콘텐츠를 **한 번에** 받는다. 단계마다 부르지 않는다 (어르신 대기 최소화).

**요청**
```
GET /api/py/session/today
X-User-Id: 550e8400-...
```

**응답 `200`**
```json
{
  "session_id": 42,
  "date": "2026-07-17",
  "week": 1,
  "domain": "지남력",
  "level": 2,
  "completed": false,
  "steps": {
    "mood": {
      "prompt": "오늘 기분은 어떠세요?",
      "choices": ["좋아요", "그저 그래요", "별로예요"]
    },
    "warmup": {
      "question_id": 101,
      "prompt": "오늘은 무슨 요일인가요?",
      "choices": ["월요일", "화요일", "수요일", "목요일"]
    },
    "main": {
      "question_id": 205,
      "prompt": "지금은 어느 계절인가요?",
      "choices": ["봄", "여름", "가을", "겨울"]
    },
    "recall": {
      "prompt": "젊으실 때 이맘때는 무엇을 하셨나요?"
    },
    "mission": {
      "text": "달력에 오늘 날짜를 표시해 보세요"
    }
  }
}
```

**필드 설명**

| 필드 | 뜻 |
|---|---|
| `session_id` | 이후 요청에 사용 |
| `level` | 서버가 정한 현재 난이도 (1~3). **프런트는 표시만** |
| `completed` | 이미 오늘 했으면 `true` → 프런트는 완료 화면으로 |
| `steps.*.choices` | 자유회상형(level 3)이면 `null` |
| `steps.recall` | `question_id` 없음. **판정하지 않는다** (정답이 없는 질문) |

> ★ `answer` 필드가 **없다.** 의도적이다.

**에러**: `401 NO_USER_ID`

---

## 4. `POST /api/py/session/{session_id}/answer` — 답 제출·판정

`warmup` 과 `main` 단계에서만 호출. `mood`·`recall`·`mission` 은 판정 없음.

**요청**
```
POST /api/py/session/42/answer
X-User-Id: 550e8400-...
```
```json
{
  "question_id": 205,
  "response": "여름"
}
```

**응답 `200` — 정답**
```json
{
  "correct": true,
  "attempts": 1,
  "message": "맞아요, 잘하셨어요!",
  "next_action": "proceed"
}
```

**응답 `200` — 1차 오답**
```json
{
  "correct": false,
  "attempts": 1,
  "message": "비슷해요, 하나만 더 생각해볼까요?",
  "next_action": "retry"
}
```

**응답 `200` — 2차 오답**
```json
{
  "correct": false,
  "attempts": 2,
  "message": "괜찮아요, 오늘은 여기까지도 잘하셨어요",
  "next_action": "proceed"
}
```

**필드 설명**

| 필드 | 뜻 |
|---|---|
| `correct` | 서버 판정 결과 |
| `attempts` | 이 문항 시도 횟수 |
| `next_action` | `retry`(다시) / `proceed`(다음으로). **프런트는 이것만 보고 분기** |
| `message` | 그대로 화면에 표시 |

> ★ **정답이 뭐였는지 알려주지 않는다.** PRD §3.4 오답 처리 원칙.
> ★ `next_action` 을 서버가 정한다. 프런트가 "2번 틀렸으니 넘어가자"를 판단하지 않는다.

**에러**: `401` / `403 NOT_YOUR_SESSION` / `404 QUESTION_NOT_FOUND` / `409 ALREADY_COMPLETED`

---

## 5. `POST /api/py/session/{session_id}/complete` — 세션 완료

⑤ 미션까지 본 뒤 호출. **여기서 난이도가 재계산된다.**

**요청**
```
POST /api/py/session/42/complete
X-User-Id: 550e8400-...
```
```json
{
  "mood": "좋아요"
}
```

**응답 `200`**
```json
{
  "session_id": 42,
  "streak_days": 5,
  "next_level": 3,
  "level_changed": true,
  "message": "5일째 연속이에요. 대단하세요!"
}
```

| 필드 | 뜻 |
|---|---|
| `streak_days` | 연속 참여일. **서버 계산** |
| `next_level` | 다음 세션 난이도 (서버가 3연속 성공/2연속 실패로 판단) |
| `level_changed` | 바뀌었으면 `true` |

> ★ 난이도 조정 로직 전체가 서버에 있다. 프런트는 결과만 받는다.

**에러**: `401` / `403` / `404` / `409 ALREADY_COMPLETED`

---

## 6. `GET /api/py/history` — 최근 7일 도장판

**요청**
```
GET /api/py/history
X-User-Id: 550e8400-...
```

**응답 `200`**
```json
{
  "streak_days": 5,
  "days": [
    { "date": "2026-07-11", "completed": true,  "domain": "지남력" },
    { "date": "2026-07-12", "completed": true,  "domain": "지남력" },
    { "date": "2026-07-13", "completed": false, "domain": null },
    { "date": "2026-07-14", "completed": true,  "domain": "지남력" },
    { "date": "2026-07-15", "completed": true,  "domain": "지남력" },
    { "date": "2026-07-16", "completed": true,  "domain": "지남력" },
    { "date": "2026-07-17", "completed": false, "domain": null }
  ]
}
```

> 정답률·점수를 반환하지 않는다. **도장판은 "했다/안 했다"만** 보여준다.
> 어르신에게 성적을 보이면 실패 경험이 된다 (PRD §3.4).

**에러**: `401`

---

## 7. `GET /api/py/health` — 상태 확인

컨테이너가 살아있는지 확인용. 인증 불필요.

**응답 `200`**
```json
{ "status": "ok", "db": "ok" }
```

> Docker healthcheck 및 터널 점검에 사용.

---

## 8. 프런트 구현 규칙

### 8.1 3상태 처리 (전 호출 필수)

| 상태 | 화면 |
|---|---|
| 로딩 | "잠시만 기다려 주세요" + 큰 글씨 |
| 성공 | 정상 화면 |
| 에러 | `message` 표시 + "다시 해보기" 버튼 |

> 강의 지적: "로딩·에러 상태 누락 → 앱이 멈춘 듯 보임"

### 8.2 절대 하지 말 것

- ❌ 정답을 프런트에 두고 비교하기
- ❌ `attempts` 를 프런트에서 세서 넘어갈지 판단하기 → `next_action` 을 쓴다
- ❌ `level` 을 프런트에서 계산하기
- ❌ `user_id` 를 URL 쿼리스트링에 넣기 → **헤더로만**

---

## 9. 목데이터 (Phase 1용)

`mocks/` 폴더에 **이 명세와 똑같은 모양**으로 만든다.

```
mocks/
├── users.json            ← 2. 응답
├── session-today.json    ← 3. 응답
├── answer-correct.json   ← 4. 정답 응답
├── answer-wrong-1.json   ← 4. 1차 오답
├── answer-wrong-2.json   ← 4. 2차 오답
├── complete.json         ← 5. 응답
└── history.json          ← 6. 응답
```

> ★ 목데이터가 명세와 같은 모양이면, Phase 3에서 **import를 fetch로 바꾸는 것만으로** 교체가 끝난다.
> 화면 코드는 거의 안 바뀐다.

---

## 10. 변경 이력

| 버전 | 날짜 | 내용 |
|---|---|---|
| v1 | 2026-07-17 | 최초 작성 |

> 기능 변경 시 **이 문서를 먼저 고치고** 버전을 올린 뒤 코드를 고친다.

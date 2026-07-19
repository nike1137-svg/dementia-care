# dementia-care — DB 스키마 (Phase 4)

- **작성일**: 2026-07-20
- **상태**: 설계 문서. Phase 4-a는 스키마만 확정 — 연결 코드·DB 파일은 아직 없다
- **DB**: SQLite (`docs/prd.md` §6 확정 사항)
- **파일 위치**: `api/data/dementia.db` (named volume 부착 대상, `docs/threat-model.md` §7.1)

---

## 1. 테이블

### 1.1 `users`

| 컬럼 | 타입 | 제약 | 뜻 |
|---|---|---|---|
| `user_id` | TEXT | PRIMARY KEY | 익명 UUID (api-spec §0.3) |
| `level` | INTEGER | 기본 1 | 현재 난이도 1~3 |
| `week` | INTEGER | 기본 1 | 커리큘럼 주차 |
| `created_at` | TEXT | | ISO 8601 시각 |

### 1.2 `daily_completions` (도장판 — A 방식)

| 컬럼 | 타입 | 제약 | 뜻 |
|---|---|---|---|
| `user_id` | TEXT | | 사용자 |
| `date` | TEXT | | `YYYY-MM-DD` |
| `completed_at` | TEXT | | ISO 8601 시각 |

- **`(user_id, date)` 복합 UNIQUE** — 하루 한 번만 기록
- 도장판(`GET /history`)과 `streak_days`는 이 테이블을 **날짜로 세어서** 계산한다 (아래 §2.1 "A 방식")

### 1.3 `session_progress` (난이도 계산용)

| 컬럼 | 타입 | 제약 | 뜻 |
|---|---|---|---|
| `session_id` | TEXT | | 세션 식별자 |
| `user_id` | TEXT | | 사용자 |
| `consecutive_correct` | INTEGER | 기본 0 | 연속 성공 횟수 |
| `consecutive_wrong` | INTEGER | 기본 0 | 연속 실패 횟수 |

- `/answer`의 최종 판정(재시도 대기 아닌 결과)마다 갱신
- `/complete`가 3연속 성공(→ `users.level` 상승) / 2연속 실패(→ `users.level` 하강)를 여기서 판단 (PRD §3.3)

---

## 2. 설계 근거

### 2.1 도장판 계산 — A 방식(이벤트 기록 후 집계)

`daily_completions`에 "완료한 날"만 행으로 쌓고, `streak_days`·최근 7일 도장판은 **조회 시점에 이 테이블을 세어서** 계산한다.
(대안 B: `users`에 `streak_days` 정수 컬럼을 두고 매번 증감시키는 방식은 채택하지 않음 — 갱신 누락·중복 증가 같은 동기화 버그 위험이 있고, A 방식은 원본 이벤트만 정확하면 항상 다시 계산해 맞출 수 있다.)

### 2.2 `attempts`(문항별 시도 횟수)는 DB에 안 넣는다

- **세션 안에서만 의미 있는 임시값**이다. 세션이 끝나면 버려도 된다 (영구 보존할 이유 없음)
- Phase 2-b-2에서 이미 프로세스 메모리(`_attempts: dict[(session_id, question_id), int]`)로 검증된 로직이 있다 — DB로 옮기면 "언제 지우나"(세션 종료 시점 정리 코드)를 새로 짜야 하고, 그 정리 로직 자체가 버그 소지가 된다
- **결론**: attempts는 계속 메모리에 둔다. 서버 재시작하면 초기화되는 것도 문제 없다 (진행 중이던 문항 재시도 상태일 뿐, 사용자 식별 데이터가 아님)

### 2.3 문항 데이터는 계속 파일(`content/questions-week1.json`)

- 문항 문구·정답·`answer_rule`은 **콘텐츠**지 사용자 데이터가 아니다 — 안 변한다(마커스님이 확정한 문항 은행)
- Phase 2-b에서 이미 검증된 로직(`find_question`, `compute_dynamic_answer`, 결정적 셔플)이 파일 구조를 전제로 짜여 있다 — DB 테이블로 옮기면 이 검증된 코드를 다시 짜야 하고 얻는 이득이 없다
- 문항을 DB로 옮기는 건 "새 주차 문항을 관리자 화면에서 추가"처럼 실제 필요가 생겼을 때 재검토

### 2.4 DB 파일 위치·보안

- `api/data/dementia.db` — SQLite 파일 하나
- **`.gitignore`에 이미 커버됨**: 기존 28행 `*.db`, 31행 `data/` 규칙이 `api/data/dementia.db`를 이미 무시한다 (`git check-ignore -v`로 확인). 사용자 데이터가 담긴 파일이라 커밋되면 안 된다 — 새 규칙을 중복 추가하지 않았다
- 컨테이너화 시(Phase 5) named volume으로 부착 (`docs/threat-model.md` §7.1) — 컨테이너를 지워도 데이터는 유지, 호스트 경로 바인드는 아님

---

## 3. 스코프 밖 (Phase 4-a에서 안 함)

- SQLite 연결 코드 (`sqlite3`/`aiosqlite` 등)
- 실제 DB 파일 생성
- `api/index.py` 수정 — 메모리 기반 로직은 Phase 4-b에서 이 스키마로 교체

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

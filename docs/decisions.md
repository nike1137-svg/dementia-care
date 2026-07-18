# 결정 기록 (Decisions)

## 2026-07-18 — postcss/next 취약점(GHSA-qx2v-qp2m-jg93) 미조치

- **무엇**: `next@16.2.10`이 물고 오는 간접 의존성 `postcss@8.4.31`의 moderate XSS 경고 2건.
- **왜 안 고치나**: postcss는 **빌드 타임 전용** 도구이고, 우리는 사용자 입력 CSS를 postcss로 처리하는 경로가 없다. → **우리 공격 표면에 닿지 않는다.** `npm audit fix --force`는 next를 9.3.3으로 다운그레이드해 프로젝트를 파괴한다.
- **재검토 시점**: Next.js가 상위 릴리스에서 postcss를 올릴 때 따라간다. `npm audit fix`는 마커스님 승인 없이 실행 금지.

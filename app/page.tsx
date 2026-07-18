"use client";

import styles from "./page.module.css";
import { useFetch } from "./lib/useFetch";
import { AsyncBoundary } from "./components/AsyncBoundary";

// Phase 3 교체: 이 URL만 "/api/py/history"로 바꾸면 실제 백엔드로 전환된다 (api-spec §9).
const HISTORY_URL = "/mocks/history.json";

// api-spec §6 GET /api/py/history 응답에서 홈이 쓰는 부분
type History = { streak_days: number };

async function loadHistory(): Promise<History> {
  const res = await fetch(HISTORY_URL);
  if (!res.ok) throw new Error(`history ${res.status}`);
  return (await res.json()) as History;
}

export default function Home() {
  const { status, data, retry } = useFetch(loadHistory);
  const streakDays = data?.streak_days ?? 0;

  return (
    <AsyncBoundary status={status} onRetry={retry}>
      <div className={styles.home}>
        <h1 className={styles.title}>새록이</h1>

        <section className={styles.streakBox} aria-label="연속 참여일">
          <span className={styles.streakLabel}>연속 참여</span>
          <span className={styles.streakNumber}>{streakDays}일</span>
        </section>

        {/* 세션 화면은 Phase 1-c-2에서. 지금은 진입 링크만. */}
        <a className={styles.button} href="/session">
          오늘 두뇌 활동 시작하기
        </a>
      </div>
    </AsyncBoundary>
  );
}

"use client";

import styles from "./done.module.css";
import { useFetch } from "../lib/useFetch";
import { AsyncBoundary } from "../components/AsyncBoundary";

// Phase 3 교체: 이 URL만 "/api/py/session/{id}/complete"(POST)로 바꾼다 (api-spec §9).
const COMPLETE_URL = "/mocks/complete.json";

// api-spec §5 complete 응답에서 완료 화면이 쓰는 부분
type Complete = {
  streak_days: number;
  mission: string;
  message: string;
};

async function loadComplete(): Promise<Complete> {
  const res = await fetch(COMPLETE_URL);
  if (!res.ok) throw new Error(`complete ${res.status}`);
  return (await res.json()) as Complete;
}

export default function DonePage() {
  const { status, data, retry } = useFetch(loadComplete);

  return (
    <AsyncBoundary status={status} onRetry={retry}>
      {data && (
        <div className={styles.done}>
          <p className={styles.message}>{data.message}</p>

          <section className={styles.streakBox} aria-label="연속 참여일">
            <span className={styles.streakLabel}>연속 참여</span>
            <span className={styles.streakNumber}>{data.streak_days}일</span>
          </section>

          <section className={styles.missionBox} aria-label="오늘의 미션">
            <span className={styles.missionLabel}>오늘의 미션</span>
            <p className={styles.missionText}>{data.mission}</p>
          </section>

          <a className={styles.button} href="/">
            홈으로
          </a>
        </div>
      )}
    </AsyncBoundary>
  );
}

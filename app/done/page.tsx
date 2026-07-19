"use client";

import styles from "./done.module.css";
import { useFetch } from "../lib/useFetch";
import { AsyncBoundary } from "../components/AsyncBoundary";

const STORAGE_KEY = "completeResult";

// api-spec §5 complete 응답에서 완료 화면이 쓰는 부분
type Complete = {
  streak_days: number;
  mission: string;
  message: string;
};

/*
 * POST /api/py/session/{id}/complete는 session_id·mood가 필요한데 둘 다
 * 세션 화면에서만 안다 — 이 화면은 그걸 재요청할 방법이 없다. 그래서 세션
 * 화면이 완료 직후 응답을 sessionStorage에 담아 넘기고, 여기서는 그걸 읽기만 한다.
 */
async function loadComplete(): Promise<Complete> {
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) throw new Error("완료 결과가 없습니다 — 세션을 먼저 완주해야 합니다");
  return JSON.parse(raw) as Complete;
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

"use client";

import styles from "./page.module.css";
import { useFetch } from "./lib/useFetch";
import { AsyncBoundary } from "./components/AsyncBoundary";
import { getOrCreateUserId } from "./lib/userId";

const HISTORY_URL = "/api/py/history";

// api-spec §6 GET /api/py/history 응답에서 홈이 쓰는 부분
type History = { streak_days: number };

async function loadHistory(): Promise<History> {
  const userId = await getOrCreateUserId();
  const res = await fetch(HISTORY_URL, { headers: { "X-User-Id": userId } });
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

        {/* 연속일 영역을 탭하면 기록 화면으로. 링크임을 밑줄+"기록 보기" 라벨로 표시(색만 X) */}
        <a
          className={styles.streakLink}
          href="/history"
          aria-label="연속 참여일, 눌러서 기록 보기"
        >
          <span className={styles.streakLabel}>연속 참여</span>
          <span className={styles.streakNumber}>{streakDays}일</span>
          <span className={styles.streakMore}>기록 보기</span>
        </a>

        {/* 세션 화면은 Phase 1-c-2에서. 지금은 진입 링크만. */}
        <a className={styles.button} href="/session">
          오늘 두뇌 활동 시작하기
        </a>
      </div>
    </AsyncBoundary>
  );
}

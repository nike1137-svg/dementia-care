"use client";

import { useCallback, useEffect, useState } from "react";
import styles from "./page.module.css";

// api-spec §6 GET /api/py/history 응답에서 홈이 쓰는 부분
type History = { streak_days: number };

// Phase 3 교체: 이 URL만 "/api/py/history"로 바꾸면 실제 백엔드로 전환된다 (api-spec §9).
const HISTORY_URL = "/mocks/history.json";

async function loadHistory(): Promise<History> {
  const res = await fetch(HISTORY_URL);
  if (!res.ok) throw new Error(`history ${res.status}`);
  return (await res.json()) as History;
}

type Status = "loading" | "success" | "error";

export default function Home() {
  const [status, setStatus] = useState<Status>("loading");
  const [streakDays, setStreakDays] = useState(0);

  const run = useCallback(() => {
    setStatus("loading");
    loadHistory()
      .then((history) => {
        setStreakDays(history.streak_days);
        setStatus("success");
      })
      .catch(() => setStatus("error"));
  }, []);

  useEffect(() => {
    run();
  }, [run]);

  return (
    <main className={styles.screen}>
      {/* 상태: 로딩 (api-spec §8.1) */}
      {status === "loading" && (
        <p className={styles.stateText}>잠시만 기다려 주세요…</p>
      )}

      {/* 상태: 에러 (api-spec §8.1) */}
      {status === "error" && (
        <div className={styles.stateBlock}>
          <p className={styles.stateText}>
            잠깐 문제가 생겼어요.
            <br />
            아래 단추를 눌러 다시 해보세요.
          </p>
          <button type="button" className={styles.button} onClick={run}>
            다시 해보기
          </button>
        </div>
      )}

      {/* 상태: 성공 — 스크롤 없이 한 화면 */}
      {status === "success" && (
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
      )}
    </main>
  );
}

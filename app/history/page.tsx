"use client";

import styles from "./history.module.css";
import { useFetch } from "../lib/useFetch";
import { AsyncBoundary } from "../components/AsyncBoundary";
import { getOrCreateUserId } from "../lib/userId";

const HISTORY_URL = "/api/py/history";

// api-spec §6 history 응답. 정답률·점수는 없다(의도적) — 도장판은 "했다/안 했다"만.
type Day = { date: string; completed: boolean; domain: string | null };
type History = { days: Day[] };

async function loadHistory(): Promise<History> {
  const userId = await getOrCreateUserId();
  const res = await fetch(HISTORY_URL, { headers: { "X-User-Id": userId } });
  if (!res.ok) throw new Error(`history ${res.status}`);
  return (await res.json()) as History;
}

// "M/D" 표기 (날짜만. 성적 아님)
function dateLabel(date: string): string {
  const [, m, d] = date.split("-");
  return `${Number(m)}/${Number(d)}`;
}

export default function HistoryPage() {
  const { status, data, retry } = useFetch(loadHistory);

  return (
    <AsyncBoundary status={status} onRetry={retry}>
      {data && (
        <div className={styles.history}>
          <h1 className={styles.title}>최근 7일</h1>

          <ol className={styles.board}>
            {data.days.map((day) => (
              <li key={day.date} className={styles.day}>
                <span className={styles.date}>{dateLabel(day.date)}</span>
                {/* 색만이 아니라 채움(모양) + 기호 + 글자로 구분 (색약 대비, PRD §4.1) */}
                <span
                  className={`${styles.stamp} ${
                    day.completed ? styles.completed : styles.missed
                  }`}
                  aria-hidden="true"
                >
                  {day.completed ? "✓" : "·"}
                </span>
                <span className={styles.dayLabel}>
                  {day.completed ? "함" : "안 함"}
                </span>
              </li>
            ))}
          </ol>

          <a className={styles.button} href="/">
            홈으로
          </a>
        </div>
      )}
    </AsyncBoundary>
  );
}

import type { ReactNode } from "react";
import type { FetchStatus } from "../lib/useFetch";
import styles from "./AsyncBoundary.module.css";

/*
 * 홈·세션·(완료·기록)이 공유하는 화면 경계 (api-spec §8.1).
 * - loading → "잠시만 기다려 주세요…"
 * - error   → 안내 문구 + "다시 해보기"(onRetry)
 * - success → children
 * 성공 화면의 바깥 틀(가운데 정렬·여백)도 여기서 한 번만 준다.
 */
export function AsyncBoundary({
  status,
  onRetry,
  children,
}: {
  status: FetchStatus;
  onRetry: () => void;
  children: ReactNode;
}) {
  return (
    <main className={styles.screen}>
      {status === "loading" && (
        <p className={styles.stateText}>잠시만 기다려 주세요…</p>
      )}

      {status === "error" && (
        <div className={styles.stateBlock}>
          <p className={styles.stateText}>
            잠깐 문제가 생겼어요.
            <br />
            아래 단추를 눌러 다시 해보세요.
          </p>
          <button
            type="button"
            className={styles.retryButton}
            onClick={onRetry}
          >
            다시 해보기
          </button>
        </div>
      )}

      {status === "success" && children}
    </main>
  );
}

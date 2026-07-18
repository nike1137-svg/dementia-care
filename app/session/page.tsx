"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import styles from "./session.module.css";

// Phase 3 교체: 이 URL만 "/api/py/session/today"로 바꾸면 실제 백엔드로 전환된다 (api-spec §9).
const SESSION_URL = "/mocks/session-today.json";

// api-spec §3 GET /api/py/session/today 응답 (answer 없음 — 의도적)
type Step = {
  prompt?: string;
  text?: string;
  choices?: string[];
  question_id?: number;
};
type Session = {
  session_id: number;
  domain: string;
  level: number;
  steps: Record<StepKey, Step>;
};

// 한 화면 = 한 단계 (api-spec §3.1). 순서 고정.
const STEP_ORDER = ["mood", "warmup", "main", "recall", "mission"] as const;
type StepKey = (typeof STEP_ORDER)[number];

async function loadSession(): Promise<Session> {
  const res = await fetch(SESSION_URL);
  if (!res.ok) throw new Error(`session ${res.status}`);
  return (await res.json()) as Session;
}

type Status = "loading" | "success" | "error";

export default function SessionPage() {
  const router = useRouter();
  const [status, setStatus] = useState<Status>("loading");
  const [session, setSession] = useState<Session | null>(null);
  const [stepIndex, setStepIndex] = useState(0);

  const run = useCallback(() => {
    setStatus("loading");
    loadSession()
      .then((s) => {
        setSession(s);
        setStepIndex(0);
        setStatus("success");
      })
      .catch(() => setStatus("error"));
  }, []);

  useEffect(() => {
    run();
  }, [run]);

  // 판정 없음(1-c-2-a): 선택지든 다음 단추든 그냥 다음 단계로.
  // 마지막(mission) 다음엔 /done 으로. (1-c-3 전까지 404여도 됨)
  const advance = useCallback(() => {
    setStepIndex((i) => {
      if (i >= STEP_ORDER.length - 1) {
        router.push("/done");
        return i;
      }
      return i + 1;
    });
  }, [router]);

  // 상태: 로딩 (홈과 동일 패턴, api-spec §8.1)
  if (status === "loading") {
    return (
      <main className={styles.screen}>
        <p className={styles.stateText}>잠시만 기다려 주세요…</p>
      </main>
    );
  }

  // 상태: 에러
  if (status === "error" || !session) {
    return (
      <main className={styles.screen}>
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
      </main>
    );
  }

  // 상태: 성공 — 현재 단계 하나만 보여준다
  const key = STEP_ORDER[stepIndex];
  const step = session.steps[key];
  const isLast = stepIndex === STEP_ORDER.length - 1;

  return (
    <main className={styles.screen}>
      <div className={styles.step}>
        <p className={styles.progress}>
          {stepIndex + 1} / {STEP_ORDER.length}
        </p>

        <h1 className={styles.prompt}>{step.prompt ?? step.text}</h1>

        {step.choices ? (
          // 선택지 단계(mood·warmup·main): 눌러도 판정 없이 다음으로 (판정은 1-c-2-b)
          <div className={styles.choices}>
            {step.choices.map((choice) => (
              <button
                key={choice}
                type="button"
                className={styles.button}
                onClick={advance}
              >
                {choice}
              </button>
            ))}
          </div>
        ) : (
          // 선택지 없는 단계(recall·mission): 다음 단추만
          <button type="button" className={styles.button} onClick={advance}>
            {isLast ? "오늘 마치기" : "다음"}
          </button>
        )}
      </div>
    </main>
  );
}

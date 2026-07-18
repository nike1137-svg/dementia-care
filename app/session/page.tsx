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
  steps: Record<StepKey, Step>;
};

// 한 화면 = 한 단계 (api-spec §3.1). 순서 고정.
const STEP_ORDER = ["mood", "warmup", "main", "recall", "mission"] as const;
type StepKey = (typeof STEP_ORDER)[number];

// 판정(answer 엔드포인트)이 붙는 단계 (api-spec §4). mood·recall·mission은 판정 없음.
const JUDGED = new Set<StepKey>(["warmup", "main"]);

// api-spec §4 answer 응답. answer(정답) 필드 없음 — correct는 판정 결과 플래그일 뿐.
type AnswerResponse = {
  correct: boolean;
  attempts: number;
  message: string;
  next_action: "retry" | "proceed";
};

async function loadSession(): Promise<Session> {
  const res = await fetch(SESSION_URL);
  if (!res.ok) throw new Error(`session ${res.status}`);
  return (await res.json()) as Session;
}

/*
 * ★ 목 판정 재현 (진짜 판정이 아니다. Phase 2에서 FastAPI가 실제로 판정한다).
 *   프런트는 정답을 모른다 — 어느 선택지가 맞는지 보지 않는다.
 *   오직 "단계 + 시도 횟수"로 어떤 목 응답을 보여줄지 스크립트할 뿐이다.
 *     - warmup: 재시도 흐름 시연 (wrong-1: 다시 → wrong-2: 넘어가기)
 *     - main  : 정답 흐름 시연 (correct, 1번째에 proceed)
 */
function mockAnswerFile(step: StepKey, attempt: number): string {
  if (step === "warmup") {
    return attempt >= 2 ? "answer-wrong-2.json" : "answer-wrong-1.json";
  }
  return "answer-correct.json";
}

async function submitMockAnswer(
  step: StepKey,
  attempt: number,
): Promise<AnswerResponse> {
  // Phase 2 교체: POST /api/py/session/{id}/answer 로 실제 제출 (서버가 판정).
  const res = await fetch(`/mocks/${mockAnswerFile(step, attempt)}`);
  if (!res.ok) throw new Error(`answer ${res.status}`);
  return (await res.json()) as AnswerResponse;
}

type Status = "loading" | "success" | "error";
type Feedback = { message: string; nextAction: "retry" | "proceed" };

export default function SessionPage() {
  const router = useRouter();
  const [status, setStatus] = useState<Status>("loading");
  const [session, setSession] = useState<Session | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [attempts, setAttempts] = useState(0);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const run = useCallback(() => {
    setStatus("loading");
    loadSession()
      .then((s) => {
        setSession(s);
        setStepIndex(0);
        setAttempts(0);
        setFeedback(null);
        setStatus("success");
      })
      .catch(() => setStatus("error"));
  }, []);

  useEffect(() => {
    run();
  }, [run]);

  // 다음 단계로. 마지막(mission) 다음엔 /done. 판정 상태 초기화.
  // ★ router.push는 상태 업데이터 밖에서 호출한다 (업데이터 안에서 부르면
  //   렌더 도중 Router 상태를 바꿔 "setState in render" 오류가 난다).
  const advance = useCallback(() => {
    setAttempts(0);
    setFeedback(null);
    if (stepIndex >= STEP_ORDER.length - 1) {
      router.push("/done");
    } else {
      setStepIndex(stepIndex + 1);
    }
  }, [stepIndex, router]);

  // 판정 단계에서 선택지 탭 → 목 응답 → next_action 으로 분기 (retry / proceed)
  const onAnswer = useCallback(
    (stepKey: StepKey) => {
      const attempt = attempts + 1;
      setAttempts(attempt);
      setSubmitting(true);
      submitMockAnswer(stepKey, attempt)
        .then((resp) => {
          setFeedback({ message: resp.message, nextAction: resp.next_action });
        })
        .catch(() => setStatus("error"))
        .finally(() => setSubmitting(false));
    },
    [attempts],
  );

  // 상태: 로딩
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

  // 상태: 성공 — 현재 단계 하나만
  const key = STEP_ORDER[stepIndex];
  const step = session.steps[key];
  const isLast = stepIndex === STEP_ORDER.length - 1;
  const judged = JUDGED.has(key);
  const proceeding = feedback?.nextAction === "proceed";

  return (
    <main className={styles.screen}>
      <div className={styles.step}>
        <p className={styles.progress}>
          {stepIndex + 1} / {STEP_ORDER.length}
        </p>

        <h1 className={styles.prompt}>{step.prompt ?? step.text}</h1>

        {/* 서버 message 그대로 표시 (api-spec §4). 부정적 통보 문구는 쓰지 않는다 (PRD §3.4) */}
        {feedback && <p className={styles.feedback}>{feedback.message}</p>}

        {proceeding ? (
          // 판정 결과 proceed → 다음 단추 하나
          <button type="button" className={styles.button} onClick={advance}>
            다음
          </button>
        ) : step.choices ? (
          // 선택지 단계. 판정 단계(warmup·main)는 onAnswer, 아니면(mood) 바로 다음.
          // retry면 이 분기로 다시 와서 선택지가 재활성화된다.
          <div className={styles.choices}>
            {step.choices.map((choice) => (
              <button
                key={choice}
                type="button"
                className={styles.button}
                disabled={submitting}
                onClick={judged ? () => onAnswer(key) : advance}
              >
                {choice}
              </button>
            ))}
          </div>
        ) : (
          // 선택지 없는 단계(recall·mission)
          <button type="button" className={styles.button} onClick={advance}>
            {isLast ? "오늘 마치기" : "다음"}
          </button>
        )}
      </div>
    </main>
  );
}

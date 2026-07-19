"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import styles from "./session.module.css";
import { useFetch } from "../lib/useFetch";
import { AsyncBoundary } from "../components/AsyncBoundary";
import { getOrCreateUserId } from "../lib/userId";

const SESSION_URL = "/api/py/session/today";

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

// api-spec §5 complete 응답. /done 화면이 sessionStorage로 이어받아 그대로 쓴다.
type CompleteResponse = {
  session_id: number;
  streak_days: number;
  next_level: number;
  level_changed: boolean;
  mission: string;
  message: string;
};

async function loadSession(): Promise<Session> {
  const userId = await getOrCreateUserId();
  const res = await fetch(SESSION_URL, { headers: { "X-User-Id": userId } });
  if (!res.ok) throw new Error(`session ${res.status}`);
  return (await res.json()) as Session;
}

async function submitAnswer(
  sessionId: number,
  questionId: number,
  response: string,
): Promise<AnswerResponse> {
  const userId = await getOrCreateUserId();
  const res = await fetch(`/api/py/session/${sessionId}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-User-Id": userId },
    body: JSON.stringify({ question_id: questionId, response }),
  });
  if (!res.ok) throw new Error(`answer ${res.status}`);
  return (await res.json()) as AnswerResponse;
}

async function submitComplete(
  sessionId: number,
  mood: string | null,
): Promise<CompleteResponse> {
  const userId = await getOrCreateUserId();
  const res = await fetch(`/api/py/session/${sessionId}/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-User-Id": userId },
    body: JSON.stringify({ mood }),
  });
  if (!res.ok) throw new Error(`complete ${res.status}`);
  return (await res.json()) as CompleteResponse;
}

type Feedback = { message: string; nextAction: "retry" | "proceed" };

export default function SessionPage() {
  const router = useRouter();
  const { status, data: session, retry, reportError } = useFetch(loadSession);
  const [stepIndex, setStepIndex] = useState(0);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [mood, setMood] = useState<string | null>(null);

  // 새 세션이 로드되면(초기·재시도) 진행 상태 초기화.
  useEffect(() => {
    if (session) {
      setStepIndex(0);
      setFeedback(null);
      setMood(null);
    }
  }, [session]);

  // 다음 단계로 (마지막 단계는 finishSession이 처리 — 여기선 안 불린다).
  const advance = useCallback(() => {
    setFeedback(null);
    setStepIndex((i) => Math.min(i + 1, STEP_ORDER.length - 1));
  }, []);

  // mood는 판정 없지만 값은 기억해뒀다가 완료 시 서버로 보낸다 (api-spec §5 요청 바디).
  const onMoodChoice = useCallback(
    (choice: string) => {
      setMood(choice);
      advance();
    },
    [advance],
  );

  // 판정 단계에서 선택지 탭 → 서버가 실제 판정 → next_action으로 분기 (retry/proceed).
  // attempts는 서버가 (session_id, question_id)로 관리 — 프런트는 세지 않는다 (§0.5).
  const onAnswer = useCallback(
    (questionId: number, response: string) => {
      if (!session) return;
      setSubmitting(true);
      submitAnswer(session.session_id, questionId, response)
        .then((resp) => {
          setFeedback({ message: resp.message, nextAction: resp.next_action });
        })
        .catch(() => reportError())
        .finally(() => setSubmitting(false));
    },
    [session, reportError],
  );

  // 마지막(mission) 단추: 완료 처리 후 /done. 결과는 sessionStorage로 넘긴다 —
  // session_id·mood는 이 화면에서만 알 수 있어 /done이 스스로 재요청할 수 없다.
  const finishSession = useCallback(() => {
    if (!session) return;
    setSubmitting(true);
    submitComplete(session.session_id, mood)
      .then((resp) => {
        sessionStorage.setItem("completeResult", JSON.stringify(resp));
        router.push("/done");
      })
      .catch(() => reportError())
      .finally(() => setSubmitting(false));
  }, [session, mood, router, reportError]);

  const key = STEP_ORDER[stepIndex];
  const step = session?.steps[key];
  const isLast = stepIndex === STEP_ORDER.length - 1;
  const judged = JUDGED.has(key);
  const proceeding = feedback?.nextAction === "proceed";

  return (
    <AsyncBoundary status={status} onRetry={retry}>
      {step && (
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
            // 선택지 단계. 판정 단계(warmup·main)는 서버로 제출, mood는 값만 기억하고 다음으로.
            // retry면 이 분기로 다시 와서 선택지가 재활성화된다.
            <div className={styles.choices}>
              {step.choices.map((choice) => (
                <button
                  key={choice}
                  type="button"
                  className={styles.button}
                  disabled={submitting}
                  onClick={
                    judged
                      ? () => onAnswer(step.question_id as number, choice)
                      : () => onMoodChoice(choice)
                  }
                >
                  {choice}
                </button>
              ))}
            </div>
          ) : (
            // 선택지 없는 단계(recall·mission)
            <button
              type="button"
              className={styles.button}
              disabled={submitting}
              onClick={isLast ? finishSession : advance}
            >
              {isLast ? "오늘 마치기" : "다음"}
            </button>
          )}
        </div>
      )}
    </AsyncBoundary>
  );
}

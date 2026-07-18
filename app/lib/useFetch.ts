"use client";

import { useCallback, useEffect, useState } from "react";

export type FetchStatus = "loading" | "success" | "error";

/*
 * api-spec §8.1 로딩/성공/에러 3상태 + fetch를 한 곳에서 관리.
 * 홈·세션·(완료·기록)이 공유한다.
 *
 * loader는 안정된 참조여야 한다(모듈 스코프 함수 권장). 인라인 함수를 넘기면
 * 매 렌더마다 바뀌어 무한 루프가 난다.
 */
export function useFetch<T>(loader: () => Promise<T>) {
  const [status, setStatus] = useState<FetchStatus>("loading");
  const [data, setData] = useState<T | null>(null);

  const retry = useCallback(() => {
    setStatus("loading");
    loader()
      .then((d) => {
        setData(d);
        setStatus("success");
      })
      .catch(() => setStatus("error"));
  }, [loader]);

  useEffect(() => {
    retry();
  }, [retry]);

  // 의존 비동기 작업(예: 답 제출) 실패를 같은 에러 화면으로 표시할 때 사용
  const reportError = useCallback(() => setStatus("error"), []);

  return { status, data, retry, reportError };
}

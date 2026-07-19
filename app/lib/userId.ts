"use client";

const STORAGE_KEY = "userId";

/*
 * api-spec §0.3: 로그인 없음. 익명 UUID를 브라우저에 저장하고 매 요청 헤더로 보낸다.
 *
 * localStorage를 쓴다(세션스토리지 아님): 세션스토리지는 탭을 닫으면 사라져서
 * 다음 날 다시 열면 새 UUID가 발급된다 — "매일 3분 습관"·연속 참여일이 그날로 끊긴다.
 * localStorage는 탭을 닫아도 남아 같은 사용자로 계속 인식된다.
 *
 * inflight로 동시 호출을 합쳐 이미 있는 사용자를 중복 발급하지 않는다
 * (React가 effect를 두 번 실행하는 개발 모드 등에서도 POST가 한 번만 나가게).
 */
let inflight: Promise<string> | null = null;

export async function getOrCreateUserId(): Promise<string> {
  const existing = localStorage.getItem(STORAGE_KEY);
  if (existing) return existing;

  if (!inflight) {
    inflight = fetch("/api/py/users", { method: "POST" })
      .then((res) => {
        if (!res.ok) throw new Error(`users ${res.status}`);
        return res.json();
      })
      .then((data: { user_id: string }) => {
        localStorage.setItem(STORAGE_KEY, data.user_id);
        return data.user_id;
      })
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}

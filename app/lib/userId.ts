"use client";

const STORAGE_KEY = "userId";
const RECOVERED_KEY = "userIdRecovered";

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

/*
 * api-spec §0.3: 서버가 이 user_id를 모르면 401 NO_USER_ID를 준다 (운영 SQLite
 * 볼륨이 초기화된 경우 등). 그런데 localStorage엔 옛 id가 그대로 남아 있어서,
 * 에러 화면의 "다시 해보기"를 눌러도 같은 id로 다시 요청해 또 401을 받는다.
 * 어르신은 브라우저 저장소를 비울 방법이 없으므로 스스로 못 벗어난다.
 *
 * 그래서 id를 버리고 화면을 처음부터 다시 로드한다. 새 id로 실패한 요청만
 * 재시도하지 않는 이유: 새 사용자는 완료 0일이라 week1 day1 문항만 유효한데,
 * 세션 중간이었다면 옛 question_id가 404 QUESTION_NOT_FOUND가 되어 또 막힌다.
 * 서버가 이미 그 사용자를 잊었으니 지킬 기록도 없다 — 새로 시작이 맞다.
 *
 * sessionStorage 플래그로 탭당 한 번만 시도한다. 새로고침 직후 또 401이면
 * (발급 자체가 안 되는 상황) 무한 새로고침 대신 에러 화면에 맡긴다.
 */
export function recoverFromUnknownUser(): void {
  if (sessionStorage.getItem(RECOVERED_KEY)) return;
  sessionStorage.setItem(RECOVERED_KEY, "1");
  localStorage.removeItem(STORAGE_KEY);
  inflight = null;
  location.reload();
}

/*
 * X-User-Id를 붙여 호출한다. 401이면 위 복구를 시작한다.
 * 호출부는 기존처럼 res.ok / error.code 로 분기하면 된다 — 복구가 시작되면
 * 어차피 페이지가 다시 로드되므로, 그 사이 던져지는 에러는 화면에 남지 않는다.
 */
export async function fetchAsUser(
  path: string,
  init?: Omit<RequestInit, "headers"> & { headers?: Record<string, string> },
): Promise<Response> {
  const userId = await getOrCreateUserId();
  const res = await fetch(path, {
    ...init,
    headers: { ...init?.headers, "X-User-Id": userId },
  });

  if (res.status === 401) {
    recoverFromUnknownUser();
  } else if (res.ok) {
    // 정상 응답을 받았으면 플래그를 비워, 나중에 또 잊히면 다시 복구할 수 있게 한다.
    sessionStorage.removeItem(RECOVERED_KEY);
  }
  return res;
}

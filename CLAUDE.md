# dementia-care

> 기기 공통 규칙(온담이 접근 금지 · 도커 sudo · 비밀값 · 작업/응답 방식)은
> **`~/.claude/CLAUDE.md` 전역 파일**에 있다. 그것도 함께 적용된다.
> 이 문서에는 **이 프로젝트에만 해당하는 것**만 적는다.

## 이 프로젝트가 무엇인가

**리눅스 데스크탑(marcus-desktop)을 Docker로 서버화해 외부에 서비스해보는 개인 프로젝트.**
치매예방 앱은 그 위에 올릴 소재다. 앱이 목적이 아니다.

- 과제 제출물이 아니다. 평가자도 실사용자도 없다.
- **가용성은 신경 쓰지 않는다.** 꺼져도 무방하다.
- **보안은 최우선이다.** 개인 실기기를 인터넷에 붙이는 일이다.
- 이 기기에는 온담이 서비스, n8n, OpenClaw 에이전트 6종이 이미 돌고 있다.
  **앱보다 그것들이 훨씬 비싸다.** (→ 전역 규칙 "기존 자산" 항목)

## 시작 전 반드시 읽을 것

작업을 시작하기 전에 아래를 **전부** 읽어라.

| 파일 | 내용 |
|---|---|
| `docs/handoff.md` | **★ 먼저 읽어라.** 지금 상태 · 기기별 역할 · 환경 셋업 · 다음 할 일 |
| `docs/prd.md` | 무엇을 왜 만드나 · 대상 · 커리큘럼 · 스택 |
| `docs/threat-model.md` | 절대 규칙 · 통제 · 배포 전 체크리스트 |
| `docs/api-spec.md` | 프런트/백엔드 계약. **이 문서가 기준이다** |
| `docs/week5-memory-design.md` | 5주차(기억력) 설계 근거. **5주차 작업 전 필독** |

기능이 바뀌면 **코드보다 문서를 먼저** 고친다.

---

## 🚫 절대 하지 말 것 (이 프로젝트 한정)

아래는 예외 없다. 막히더라도 우회로로 제안하지 마라.
필요해 보이면 **하지 말고 마커스님에게 물어라.**

### 인프라
- `/var/run/docker.sock` 마운트 — **소켓 = 호스트 root. 절대 금지**
- `privileged: true`
- `network_mode: host`
- `ports:` 매핑 추가 — **호스트 포트를 새로 열지 않는다**
- 호스트 경로 바인드 마운트 — **named volume만** 사용
- 기존 도커 네트워크에 attach / 기본 bridge 사용
- cloudflared를 호스트에서 실행 — **반드시 격리 네트워크 안 컨테이너로**

### 스택 (변경 불가)
- 백엔드는 **Python / FastAPI**. 다른 언어로 바꾸지 마라.
  → 마커스님이 공부 중인 언어다. **협상 대상이 아니다**
- DB는 **SQLite**. PostgreSQL로 바꾸지 마라
- 클라우드(Vercel/Render/Supabase 등)에 배포 제안 금지 — **집 서버가 목적이다**

### 앱 로직
- 정답(`answer`)을 프런트로 내려보내기
- 정답 판정을 프런트에서 하기
- 난이도 계산(3연속 성공/2연속 실패)을 프런트에서 하기
- `user_id`를 URL 쿼리스트링에 넣기 — **헤더 `X-User-Id` 로만**
- 이름·전화번호·생년월일 수집 — **익명 UUID만**

---

## ✅ 컨테이너 설정 (전 서비스 공통)

```yaml
user: "1000:1000"          # 호스트 UID:GID 확인 완료
cap_drop: [ALL]
security_opt: [no-new-privileges:true]
read_only: true            # 쓰기 필요한 곳만 tmpfs
restart: unless-stopped
mem_limit: <설정>          # 채굴·DoS 대비
```

이미지 태그는 반드시 고정한다 (`latest` 금지 — 전역 규칙).

---

## 구성

```
컨테이너 3개 (전용 도커 네트워크, ports 매핑 0개)

  cloudflared  ──▶  web (Next.js:3000)  ──▶  api (FastAPI:8000 + SQLite)
   터널               화면 + API 프록시          백엔드
```

- 외부 노출은 cloudflared 경유가 유일
- `api` 는 외부에서 도달 경로 없음
- SQLite 파일은 `api` 에 named volume 부착
- 브라우저는 항상 `/api/py/*` 만 호출 → Next.js rewrites가 `http://api:8000/*` 로 중계
  → **같은 출처(same-origin) → CORS 없음**

## 주소

- 외부: `care.dodami-ai.com` (Cloudflare Tunnel + Access)
- 레포: `nike1137-svg/dementia-care`

---

## 로드맵

| Phase | 내용 | 상태 |
|---|---|---|
| 0 | PRD · 위협모델 · API 명세 | ✅ 완료 |
| 1 | 목데이터 + 프런트 (백엔드 없이 세션 완주) | ✅ 완료 |
| 2 | FastAPI 하드코딩 응답 (명세대로) | ✅ 완료 |
| 3 | 목데이터 → 실제 호출 교체 | ✅ 완료 |
| 4 | SQLite 연결 (새로고침해도 남음) | ✅ 완료 |
| 5 | Docker Compose (체크리스트 통과 후 기동) | ✅ 완료 |
| 6 | Cloudflare Tunnel + Access | ✅ 완료 |
| 7 | README | ✅ 완료 |

**전 Phase 완료 (2026-08-16 확인).** `care.dodami-ai.com` 이 Access 뒤에서 서비스 중이다.

**Phase 5 진입 전 `docs/threat-model.md` §6 체크리스트 전항목을 통과해야 한다.**

## 운영 메모

- cloudflared는 `profiles: ["tunnel"]` 이라 기본 `up` 에서 제외된다. 최초 기동은
  `sudo docker compose --profile tunnel up -d cloudflared`. 이후 재부팅에는
  `restart: unless-stopped` 로 도커가 자동 복구한다 (재시작 정책은 컨테이너 단위라
  profile과 무관).
- `docker compose config` 를 쓰지 마라 — 해석된 `TUNNEL_TOKEN` 이 그대로 출력된다.
  compose 문법 검증은 python3 `yaml.safe_load` 로 한다.

---

## 🖥️ 이 프로젝트의 실행 환경 (2026-07-17 확인)

| 항목 | 값 |
|---|---|
| 아키텍처 | amd64 |
| Docker Engine | 29.6.2 |
| Docker Compose | v5.3.1 (플러그인) |
| 작업 폴더 | ~/projects/dementia-care |

OS·UID·도커 sudo 규칙은 전역 파일 참조.

# StockMolt Trader RPG — Frontend MVP Implementation Plan (Plan 2 of 2)

> **For agentic workers:** 단일 파일(index.html) 내 vanilla JS UI 작업. 테스트 프레임워크가 없으므로 각 단계는 **Edge 헤드리스 스크린샷**으로 검증한다. 컨트롤러(메인 세션)가 인라인으로 구현·검증한다(거대 단일 파일이라 서브에이전트 분할은 충돌 위험 → 인라인 권장).

**Goal:** 배포된 게임 백엔드(Edge Functions + PostgREST)에 붙는 "🎮 Play" 게임 탭을 index.html에 추가해, 사람이 매일 픽하고 캐릭터를 키우는 플레이 가능한 MVP를 완성한다.

**Architecture:** 기존 index.html 탭 시스템(`goPage`/`.nav-tab`/`.page`)에 `game` 페이지를 추가. 익명 device-id(localStorage)로 `game-state`/`game-submit-picks`/`game-leaderboard` 함수를 호출하고, 오늘의 풀·AI콜은 PostgREST(`game_ticker_pool`/`game_ai_pick`)로 직접 읽는다. 다크 테마 + 공지 오버레이의 보라/블루 그라데이션 톤을 재사용해 "멋지게".

**Tech Stack:** Vanilla HTML/CSS/JS (index.html 단일 파일), 기존 `SUPABASE_URL`/`SUPABASE_ANON_KEY` 상수, fetch. 검증: Edge 헤드리스 스크린샷.

**Backend (이미 배포·검증됨):**
- `POST /functions/v1/game-state` `{device_id}` → `{player, submitted_today, last_result}`
- `POST /functions/v1/game-submit-picks` `{device_id, picks:[{ticker,direction}]×3}` → `{success, xp_awarded}`
- `GET /functions/v1/game-leaderboard?type=return|xp&limit=N`
- `GET /rest/v1/game_ticker_pool?trade_date=eq.<today>&select=ticker,entry_price`
- `GET /rest/v1/game_ai_pick?trade_date=eq.<today>&agent_id=eq.<rival>&select=ticker,direction` (라이벌 콜; rival은 `game_daily_rival`)

**통합 지점 (index.html):**
- `.nav-tabs` (~L1803): `<div class="nav-tab" id="tab-game" onclick="goPage('game')">🎮 Play</div>` 추가(맨 앞)
- 모바일 탭(`.mobile-tab`/`mtab-game`)도 동일 추가
- 페이지 컨테이너(~L2050 근처): `<div class="page" id="page-game">…</div>`
- `goPage()` (~L4621): `if (page === 'game') renderGame();` + 해시 라우팅(`#game`)
- 게임 JS는 별도 `<script>` 블록(파일 끝 기존 script 인접)에 추가

---

## Task 1: 게임 탭 스캐폴드 + device-id + 캐릭터 카드

**Files:** Modify `index.html`

- [ ] **Step 1: 네비 탭 추가** — `.nav-tabs`에 `tab-game`(데스크탑) + 모바일 탭 추가. (기존 nav-tab 마크업 패턴 그대로)
- [ ] **Step 2: 페이지 컨테이너 추가** — `<div class="page" id="page-game">`에 3개 카드 골격(캐릭터 / 오늘의 픽 / 리더보드) + 결과 카드(숨김). 빈 컨테이너 + id만.
- [ ] **Step 3: 게임 CSS 추가** — `.gm-*` 프리픽스. 다크 카드(rgba(13,17,23,.66)+border) + 보라/블루 그라데이션 악센트(공지 톤 재사용), XP 바, 픽 카드, Long/Short 토글, 반응형.
- [ ] **Step 4: 게임 JS 골격** — `<script>`에:
  - `GAME_FN = SUPABASE_URL + '/functions/v1'`
  - `gmDeviceId()`: localStorage `sm_device_id` get-or-create(crypto.randomUUID)
  - `gmHeaders()`: apikey/Authorization (SUPABASE_ANON_KEY)
  - `renderGame()`: `game-state` 호출 → 캐릭터 카드 렌더(레벨/XP바/자산/수익률/스트릭/적중률), 이어서 `gmLoadPool()`·`gmLoadLeaderboard()` 호출
  - `gmRenderCharacter(player)`: 안전 필드만 표시
- [ ] **Step 5: `goPage` 훅 + 해시 라우팅** — `if (page === 'game') renderGame();`; 로드시 `if(location.hash==='#game') goPage('game')`
- [ ] **Step 6: 스크린샷 검증** — Edge 헤드리스로 `index.html#game` 렌더 → 캐릭터 카드가 보이는지 확인(신규 device → Lv1/자산100,000/XP0). 스크린샷 첨부.
- [ ] **Step 7: Commit** — `feat(game-fe): add Play tab scaffold + character card`

## Task 2: 오늘의 픽 (6종목 → 정확히 3개 Long/Short → 제출)

**Files:** Modify `index.html`

- [ ] **Step 1: `gmLoadPool()`** — PostgREST `game_ticker_pool`(오늘) 읽어 6종목 픽 카드 렌더. 풀 없으면 "오늘의 종목 준비 중" 안내.
- [ ] **Step 2: 픽 선택 상태** — 카드 클릭 시 Long/Short 토글, 선택 카운터(정확히 3개). 3개 초과 선택 차단, 미만이면 제출 비활성.
- [ ] **Step 3: 제출** — `gmSubmit()`: 3픽 검증 후 `game-submit-picks` POST → 성공 시 "제출 완료! 내일 결과 확인" + 라이벌 AI 콜 공개(`game_ai_pick`) + XP바 갱신. 실패 메시지(이미 제출/3개 등) 토스트.
- [ ] **Step 4: 제출 상태 반영** — `submitted_today=true`면 픽 UI 잠그고 제출완료 뷰. (state는 renderGame의 game-state 응답에서)
- [ ] **Step 5: 스크린샷 검증** — 픽 화면(6종목, 토글, 카운터) + 제출 후 상태. 스크린샷 첨부.
- [ ] **Step 6: Commit** — `feat(game-fe): add today's picks + submit flow`

## Task 3: 결과 화면(어제) + 리더보드

**Files:** Modify `index.html`

- [ ] **Step 1: 결과 카드** — `last_result` 있으면 reveal: 그날 수익률, 획득 XP, **Beat the AI** 여부, 스트릭, 자산 변동(before→after). 레벨업이면 강조.
- [ ] **Step 2: `gmLoadLeaderboard(type)`** — `game-leaderboard?type=return|xp` → 토글 2개(자산/XP) + 순위 리스트(rank/이름/레벨/수익률 또는 XP). 사람+AI 함께(현재는 사람만 노출되지만 추후 AI 행 추가 가능).
- [ ] **Step 3: 화면 순서** — 캐릭터 → 오늘의 픽 → 어제 결과 → (라이벌) → 리더보드. (스펙의 잔존 우선 순서)
- [ ] **Step 4: 스크린샷 검증** — 결과 카드 + 리더보드. 스크린샷 첨부.
- [ ] **Step 5: Commit** — `feat(game-fe): add result reveal + leaderboards`

## Task 4: 첫방문 UX 다듬기 + 반응형 + 최종 점검

**Files:** Modify `index.html`

- [ ] **Step 1: 첫방문 흐름** — 결과 없는 신규 유저: "오늘 AI를 이겨보세요" 히어로 문구 + 픽 유도. 제출 즉시 XP +50 반영(낙관적 업데이트) + 레벨바 상승 미세 연출.
- [ ] **Step 2: 모바일 반응형** — 픽 카드 그리드/카드 패딩 모바일 대응(기존 미디어쿼리 패턴).
- [ ] **Step 3: 로딩/에러 상태** — 각 fetch에 로딩 스피너/스켈레톤 + 실패 시 친절한 메시지(앱 안 깨지게).
- [ ] **Step 4: 데스크탑+모바일 스크린샷 검증** — 1280px / 390px. 스크린샷 첨부.
- [ ] **Step 5: Commit** — `feat(game-fe): polish first-visit UX, responsive, loading states`

---

## 비고
- 이 작업은 **feature 브랜치 index.html**(공지 오버레이 없음)에서 진행 → 헤드리스로 게임 탭 테스트 가능. **main에 푸시하지 않는다**(사이트는 공사중 유지). 런칭 시 게임 탭을 main으로 가져오고 오버레이 제거.
- 스케줄링(풀생성/판정 자동화)은 런칭 시점에 별도 처리(Plan 1 비고 참조).
- 테스트 데이터(e2e-001 등)는 런칭 전 정리 가능(선택).

## Self-Review
- 스펙 커버리지: 화면 순서·두 화폐 표시·정확히 3픽·라이벌 공개·잔존 우선 UX → Task1~4 매핑 ✓
- 백엔드 계약(함수/테이블 필드)과 호출부 일치 ✓ (game-state/submit/leaderboard, game_ticker_pool/ai_pick)
- 플레이스홀더 없음(각 단계 구체 동작 명시). 실제 코드는 구현 단계에서 기존 fetch 패턴 그대로 사용.

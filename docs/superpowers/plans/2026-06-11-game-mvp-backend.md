# StockMolt Trader RPG — Backend MVP Implementation Plan (Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 캐릭터 성장 투자 예측 게임의 백엔드(DB + Edge Functions + 일일 풀 생성/판정 엔진)를 구축한다. 사람 없이 curl로 끝까지 검증 가능한 상태가 목표.

**Architecture:** Supabase Postgres에 게임 테이블 6개를 만들고, 모든 쓰기·판정은 service-role Edge Function(Deno/TS)으로 처리한다. 시세는 기존 `get-price` 함수를 재사용(close-to-close). 핵심 계산(수익률·XP·레벨·스트릭)은 순수 함수 모듈 `_shared/game_logic.ts`로 분리해 Deno 단위테스트로 검증한다. AI 라이벌은 기존 Groq 무료티어로 6종목 directional call(비용 0).

**Tech Stack:** Supabase (Postgres + Edge Functions, Deno), TypeScript, `@supabase/supabase-js@2`, 기존 `get-price` 함수, Groq API(무료티어). 테스트: `deno test`(추가 인프라 없음).

**기존 패턴(반드시 따를 것):**
- Edge function: `supabase/functions/<name>/index.ts`, `Deno.serve`, `corsHeaders`, `createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)`. 샘플: `supabase/functions/create-post/index.ts`.
- Migration: `supabase/migrations/NNN_*.sql`, `CREATE TABLE IF NOT EXISTS`, `gen_random_uuid()`, RLS는 anon read-only + service-role write. 샘플: `001_predictions_table.sql`, `002_predictions_rls.sql`.
- 시세: `GET ${SUPABASE_URL}/functions/v1/get-price?ticker=NVDA` → `{ "price": <number> }`.
- `_shared/` 폴더는 함수로 배포되지 않는 공용 모듈 위치(언더스코어 시작).

**MVP 설계 출처:** `docs/superpowers/specs/2026-06-11-character-progression-game-design.md`

**판정 흐름 결정(중요):** 결과 화면이 재방문 트리거이므로 "view XP"도 판정 시점에 ledger로 적립하되, 사용자가 결과를 *봐야* 보상이 드러난다(자산 변동·Beat AI·레벨업 reveal). 별도 view 엔드포인트는 MVP에서 만들지 않는다(어뷰즈 방지·단순화).

---

## File Structure

생성/수정 파일과 책임:

- `supabase/migrations/004_game_tables.sql` — 게임 테이블 6개 + 인덱스 + RLS (생성)
- `supabase/functions/_shared/game_logic.ts` — 순수 계산(수익률/XP/레벨/스트릭/평균) (생성)
- `supabase/functions/_shared/game_logic_test.ts` — 위 모듈 Deno 단위테스트 (생성)
- `supabase/functions/game-state/index.ts` — device_id로 player get-or-create + 오늘 상태/최근 결과 반환 (생성)
- `supabase/functions/game-submit-picks/index.ts` — 정확히 3픽 검증·저장 + 제출 XP+50 (생성)
- `supabase/functions/game-leaderboard/index.ts` — 수익률/XP 리더보드 안전 컬럼만 반환 (생성)
- `supabase/functions/game-generate-pool/index.ts` — 오늘 6종목 풀 생성 + entry 시세 + 라이벌 선정 + AI 6콜 (생성, cron)
- `supabase/functions/game-resolve/index.ts` — exit 시세·판정·일일결과 집계·XP/레벨/스트릭/자산 갱신 (생성, cron, 멱등)
- `scripts/game_schedule.ps1` — 일일 풀생성/판정 트리거(Windows 작업 스케줄러용 curl) (생성)

> 보안 메모: `players`, `game_pick`, `game_daily_result`, `game_xp_ledger`는 device_id 등 민감정보 포함 → anon 직접 read 금지(RLS 정책 없음). 외부 노출은 Edge Function(game-state, game-leaderboard)으로만. `game_ticker_pool`, `game_ai_pick`은 비민감 → anon read 허용(프론트가 PostgREST로 직접 조회).

---

## Task 1: DB 마이그레이션 (게임 테이블 + RLS)

**Files:**
- Create: `supabase/migrations/004_game_tables.sql`

- [ ] **Step 1: 마이그레이션 파일 작성**

```sql
-- supabase/migrations/004_game_tables.sql
-- StockMolt Trader RPG (게임 MVP) 테이블.
-- 쓰기/판정은 service-role Edge Function 전용. anon은 비민감 테이블만 read.

-- 1) players: 익명 device-id 기반 플레이어
CREATE TABLE IF NOT EXISTS players (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id        text NOT NULL UNIQUE,
  email            text,
  display_name     text,
  level            int  NOT NULL DEFAULT 1,
  xp               int  NOT NULL DEFAULT 0,
  streak_current   int  NOT NULL DEFAULT 0,
  streak_best      int  NOT NULL DEFAULT 0,
  capital          numeric NOT NULL DEFAULT 100000,
  last_played_date date,
  claimed          boolean NOT NULL DEFAULT false,
  created_at       timestamptz NOT NULL DEFAULT now()
);

-- 2) game_ticker_pool: 그날 제공 종목 + 진입/청산 시세(감사용)
CREATE TABLE IF NOT EXISTS game_ticker_pool (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trade_date     date NOT NULL,
  ticker         text NOT NULL,
  market         text NOT NULL DEFAULT 'US',
  sector         text,
  entry_price    numeric,
  exit_price     numeric,
  entry_price_at timestamptz,
  exit_price_at  timestamptz,
  price_source   text,
  resolved       boolean NOT NULL DEFAULT false,
  UNIQUE (trade_date, ticker)
);

-- 3) game_daily_rival: 그날의 고정 라이벌 AI(제출 전 확정)
CREATE TABLE IF NOT EXISTS game_daily_rival (
  trade_date date PRIMARY KEY,
  agent_id   uuid NOT NULL REFERENCES agents(id) ON DELETE RESTRICT
);

-- 4) game_pick: 사용자 픽 (하루 정확히 3개)
CREATE TABLE IF NOT EXISTS game_pick (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id   uuid NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  trade_date  date NOT NULL,
  ticker      text NOT NULL,
  direction   text NOT NULL CHECK (direction IN ('long','short')),
  created_at  timestamptz NOT NULL DEFAULT now(),
  resolved    boolean NOT NULL DEFAULT false,
  return_pct  numeric,
  correct     boolean,
  UNIQUE (player_id, trade_date, ticker)
);

-- 5) game_ai_pick: 라이벌 AI 콜 (6종목 전체)
CREATE TABLE IF NOT EXISTS game_ai_pick (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id    uuid NOT NULL REFERENCES agents(id) ON DELETE RESTRICT,
  trade_date  date NOT NULL,
  ticker      text NOT NULL,
  direction   text NOT NULL CHECK (direction IN ('long','short')),
  return_pct  numeric,
  correct     boolean,
  UNIQUE (agent_id, trade_date, ticker)
);

-- 6) game_daily_result: 플레이어 일일 집계 (결과화면/리더보드/XP 정합성)
CREATE TABLE IF NOT EXISTS game_daily_result (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id        uuid NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  trade_date       date NOT NULL,
  picks_count      int  NOT NULL,
  avg_return_pct   numeric NOT NULL,
  correct_count    int  NOT NULL,
  win_rate_daily   numeric NOT NULL,
  capital_before   numeric NOT NULL,
  capital_after    numeric NOT NULL,
  xp_earned        int  NOT NULL,
  beat_ai          boolean NOT NULL,
  ai_agent_id      uuid,
  ai_avg_return_pct numeric,
  resolved_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (player_id, trade_date)
);

-- 7) game_xp_ledger: XP 원장 (append-only, 중복지급 방지)
CREATE TABLE IF NOT EXISTS game_xp_ledger (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id   uuid NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  trade_date  date,
  reason      text NOT NULL,
  xp_delta    int  NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (player_id, trade_date, reason)
);

CREATE INDEX IF NOT EXISTS idx_game_pick_player_date ON game_pick(player_id, trade_date);
CREATE INDEX IF NOT EXISTS idx_game_pick_unresolved ON game_pick(trade_date) WHERE resolved = false;
CREATE INDEX IF NOT EXISTS idx_game_ai_pick_date ON game_ai_pick(trade_date);
CREATE INDEX IF NOT EXISTS idx_game_pool_unresolved ON game_ticker_pool(trade_date) WHERE resolved = false;
CREATE INDEX IF NOT EXISTS idx_players_capital ON players(capital DESC);
CREATE INDEX IF NOT EXISTS idx_players_xp ON players(xp DESC);

-- RLS
ALTER TABLE players            ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_ticker_pool   ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_daily_rival   ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_pick          ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_ai_pick       ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_daily_result  ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_xp_ledger     ENABLE ROW LEVEL SECURITY;

-- 비민감 테이블만 anon read 허용 (프론트 직접 조회용). 쓰기 정책 없음 = service-role 전용.
CREATE POLICY "pool_anon_read"   ON game_ticker_pool FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "rival_anon_read"  ON game_daily_rival FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "aipick_anon_read" ON game_ai_pick     FOR SELECT TO anon, authenticated USING (true);
-- players / game_pick / game_daily_result / game_xp_ledger: anon 정책 없음 → Edge Function(service-role)으로만 접근.
```

- [ ] **Step 2: 마이그레이션 적용**

Run: `supabase db push`
Expected: `Applying migration 004_game_tables.sql...` 성공 출력. (오류 시 `supabase link` 상태 확인)

> ⚠️ 비용/배포 주의: `supabase db push`는 원격 DB를 변경합니다. 실행 전 지크님 승인 필요.

- [ ] **Step 3: 테이블 생성 확인**

Run: `supabase db dump --data-only=false --schema public | findstr /C:"CREATE TABLE \"public\".\"game_"`
Expected: `players`, `game_ticker_pool`, `game_daily_rival`, `game_pick`, `game_ai_pick`, `game_daily_result`, `game_xp_ledger` 7개 테이블 확인.

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/004_game_tables.sql
git commit -m "feat(game): add game MVP tables and RLS"
```

---

## Task 2: 순수 계산 모듈 + 단위테스트 (TDD 핵심)

**Files:**
- Create: `supabase/functions/_shared/game_logic.ts`
- Test: `supabase/functions/_shared/game_logic_test.ts`

- [ ] **Step 1: 실패하는 테스트 작성**

```ts
// supabase/functions/_shared/game_logic_test.ts
import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  levelFromXp,
  computeReturnPct,
  isCorrect,
  resultXp,
  nextStreak,
  avg,
  XP,
} from "./game_logic.ts";

Deno.test("levelFromXp: 경계값", () => {
  assertEquals(levelFromXp(0), 1);
  assertEquals(levelFromXp(99), 1);
  assertEquals(levelFromXp(100), 2);
  assertEquals(levelFromXp(250), 3);
  assertEquals(levelFromXp(5200), 10);
  assertEquals(levelFromXp(99999), 10);
});

Deno.test("computeReturnPct: long/short 부호", () => {
  assertEquals(computeReturnPct("long", 100, 110), 10);
  assertEquals(computeReturnPct("short", 100, 110), -10);
  assertEquals(computeReturnPct("short", 100, 90), 10);
});

Deno.test("isCorrect: 양수만 정답", () => {
  assertEquals(isCorrect(0.1), true);
  assertEquals(isCorrect(0), false);
  assertEquals(isCorrect(-1), false);
});

Deno.test("avg: 평균/빈배열", () => {
  assertEquals(avg([10, -10, 4]), 4 / 3);
  assertEquals(avg([]), 0);
});

Deno.test("nextStreak: 연속/끊김", () => {
  assertEquals(nextStreak(2, true), 3);
  assertEquals(nextStreak(5, false), 1);
});

Deno.test("resultXp: 합산과 내역", () => {
  const r = resultXp({ correctCount: 2, beatAi: true, newStreak: 3 });
  // view_result 30 + correct 2*10 + beat_ai 30 + streak_3 50 = 130
  assertEquals(r.total, 130);
  assertEquals(r.breakdown.length, 4);
});

Deno.test("resultXp: 무적중·패배·스트릭1", () => {
  const r = resultXp({ correctCount: 0, beatAi: false, newStreak: 1 });
  assertEquals(r.total, XP.RESULT); // view_result 30만
  assertEquals(r.breakdown.length, 1);
});
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `deno test supabase/functions/_shared/game_logic_test.ts`
Expected: FAIL — `Module not found "./game_logic.ts"` (구현 전).

- [ ] **Step 3: 최소 구현 작성**

```ts
// supabase/functions/_shared/game_logic.ts
// 순수 계산 모듈 — I/O 없음. Edge Function들이 import.

export const LEVEL_THRESHOLDS = [0, 100, 250, 500, 850, 1300, 1900, 2700, 3800, 5200];

export function levelFromXp(xp: number): number {
  let level = 1;
  for (let i = 0; i < LEVEL_THRESHOLDS.length; i++) {
    if (xp >= LEVEL_THRESHOLDS[i]) level = i + 1;
  }
  return level;
}

export function computeReturnPct(direction: "long" | "short", entry: number, exit: number): number {
  const raw = ((exit - entry) / entry) * 100;
  return direction === "long" ? raw : -raw;
}

export function isCorrect(returnPct: number): boolean {
  return returnPct > 0;
}

export function avg(nums: number[]): number {
  if (nums.length === 0) return 0;
  return nums.reduce((s, n) => s + n, 0) / nums.length;
}

export function nextStreak(prevStreak: number, playedPrevTradeDate: boolean): number {
  return playedPrevTradeDate ? prevStreak + 1 : 1;
}

export const XP = {
  SUBMIT: 50,
  RESULT: 30,
  CORRECT_EACH: 10,
  BEAT_AI: 30,
  STREAK_3: 50,
  STREAK_7: 150,
};

export interface ResultXpInput {
  correctCount: number;
  beatAi: boolean;
  newStreak: number;
}

export function resultXp(
  { correctCount, beatAi, newStreak }: ResultXpInput,
): { total: number; breakdown: { reason: string; xp: number }[] } {
  const breakdown: { reason: string; xp: number }[] = [];
  breakdown.push({ reason: "view_result", xp: XP.RESULT });
  if (correctCount > 0) breakdown.push({ reason: "correct_bonus", xp: correctCount * XP.CORRECT_EACH });
  if (beatAi) breakdown.push({ reason: "beat_ai", xp: XP.BEAT_AI });
  if (newStreak === 3) breakdown.push({ reason: "streak_3", xp: XP.STREAK_3 });
  if (newStreak === 7) breakdown.push({ reason: "streak_7", xp: XP.STREAK_7 });
  const total = breakdown.reduce((s, b) => s + b.xp, 0);
  return { total, breakdown };
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `deno test supabase/functions/_shared/game_logic_test.ts`
Expected: PASS — `ok | 7 passed`.

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/_shared/game_logic.ts supabase/functions/_shared/game_logic_test.ts
git commit -m "feat(game): add pure game logic module with deno tests"
```

---

## Task 3: game-state Edge Function (플레이어 get-or-create + 상태)

**Files:**
- Create: `supabase/functions/game-state/index.ts`

- [ ] **Step 1: 함수 작성**

```ts
// supabase/functions/game-state/index.ts
// POST { device_id, display_name? } → player + 오늘 픽 여부 + 직전 미확인 결과
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

function todayUtc(): string {
  return new Date().toISOString().slice(0, 10);
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const { device_id, display_name } = await req.json();
    if (!device_id || typeof device_id !== "string") {
      return new Response(JSON.stringify({ success: false, error: "Missing device_id" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }
    const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

    // get-or-create
    let { data: player } = await supabase.from("players").select("*").eq("device_id", device_id).maybeSingle();
    if (!player) {
      const name = (typeof display_name === "string" && display_name.trim()) ? display_name.trim().slice(0, 24)
        : `Trader-${device_id.slice(0, 6)}`;
      const { data: created, error: insErr } = await supabase.from("players")
        .insert({ device_id, display_name: name }).select("*").single();
      if (insErr) throw insErr;
      player = created;
    }

    const today = todayUtc();
    const { count: pickCount } = await supabase.from("game_pick")
      .select("id", { count: "exact", head: true })
      .eq("player_id", player.id).eq("trade_date", today);

    // 가장 최근 일일 결과(있으면 결과화면 reveal 용)
    const { data: lastResult } = await supabase.from("game_daily_result")
      .select("*").eq("player_id", player.id).order("trade_date", { ascending: false }).limit(1).maybeSingle();

    const safePlayer = {
      id: player.id, display_name: player.display_name, level: player.level, xp: player.xp,
      streak_current: player.streak_current, streak_best: player.streak_best,
      capital: player.capital, claimed: player.claimed,
    };

    return new Response(JSON.stringify({
      success: true,
      player: safePlayer,
      submitted_today: (pickCount ?? 0) > 0,
      last_result: lastResult ?? null,
    }), { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  } catch (err) {
    console.error("game-state error:", err);
    return new Response(JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }
});
```

- [ ] **Step 2: 배포** (⚠️ 배포 — 지크님 승인 필요)

Run: `supabase functions deploy game-state`
Expected: `Deployed Function game-state` 출력.

- [ ] **Step 3: curl로 검증 (신규 플레이어 생성)**

Run (PowerShell, `<ANON>`는 실제 anon key):
```powershell
curl -s -X POST "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1/game-state" -H "Content-Type: application/json" -H "apikey: <ANON>" -H "Authorization: Bearer <ANON>" -d '{\"device_id\":\"test-device-001\"}'
```
Expected: `{"success":true,"player":{... "level":1,"xp":0,"capital":100000 ...},"submitted_today":false,"last_result":null}`. 같은 명령 재실행 시 같은 player(중복 생성 안 됨) 확인.

- [ ] **Step 4: Commit**

```bash
git add supabase/functions/game-state/index.ts
git commit -m "feat(game): add game-state edge function (get-or-create player)"
```

---

## Task 4: game-submit-picks Edge Function (정확히 3픽 + 제출 XP)

**Files:**
- Create: `supabase/functions/game-submit-picks/index.ts`

- [ ] **Step 1: 함수 작성**

```ts
// supabase/functions/game-submit-picks/index.ts
// POST { device_id, picks:[{ticker,direction}] } — 오늘 풀의 종목 중 정확히 3개, 하루 1회.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { XP } from "../_shared/game_logic.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};
const todayUtc = () => new Date().toISOString().slice(0, 10);

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const { device_id, picks } = await req.json();
    if (!device_id || !Array.isArray(picks)) {
      return new Response(JSON.stringify({ success: false, error: "Missing device_id or picks" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }
    if (picks.length !== 3) {
      return new Response(JSON.stringify({ success: false, error: "정확히 3개를 선택해야 합니다" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }
    for (const p of picks) {
      if (!p || typeof p.ticker !== "string" || !["long", "short"].includes(p.direction)) {
        return new Response(JSON.stringify({ success: false, error: "Invalid pick format" }),
          { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
      }
    }
    const tickers = picks.map((p) => p.ticker);
    if (new Set(tickers).size !== 3) {
      return new Response(JSON.stringify({ success: false, error: "종목이 중복되었습니다" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const today = todayUtc();

    // 오늘 풀 종목 검증
    const { data: pool } = await supabase.from("game_ticker_pool")
      .select("ticker").eq("trade_date", today);
    const poolTickers = new Set((pool ?? []).map((r) => r.ticker));
    if (poolTickers.size === 0) {
      return new Response(JSON.stringify({ success: false, error: "오늘의 종목이 아직 준비되지 않았습니다" }),
        { status: 409, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }
    for (const t of tickers) {
      if (!poolTickers.has(t)) {
        return new Response(JSON.stringify({ success: false, error: `오늘 풀에 없는 종목: ${t}` }),
          { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } });
      }
    }

    // 플레이어
    const { data: player } = await supabase.from("players").select("id").eq("device_id", device_id).maybeSingle();
    if (!player) {
      return new Response(JSON.stringify({ success: false, error: "Unknown player. Call game-state first." }),
        { status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    // 하루 1회
    const { count: existing } = await supabase.from("game_pick")
      .select("id", { count: "exact", head: true }).eq("player_id", player.id).eq("trade_date", today);
    if ((existing ?? 0) > 0) {
      return new Response(JSON.stringify({ success: false, error: "오늘은 이미 제출했습니다" }),
        { status: 409, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    // 픽 저장
    const rows = picks.map((p) => ({ player_id: player.id, trade_date: today, ticker: p.ticker, direction: p.direction }));
    const { error: pickErr } = await supabase.from("game_pick").insert(rows);
    if (pickErr) throw pickErr;

    // 제출 XP +50 (멱등: ledger UNIQUE(player_id,trade_date,reason))
    const { error: ledgerErr } = await supabase.from("game_xp_ledger")
      .insert({ player_id: player.id, trade_date: today, reason: "submit_pick", xp_delta: XP.SUBMIT });
    if (!ledgerErr) {
      await supabase.rpc("increment_player_xp", { p_player_id: player.id, p_delta: XP.SUBMIT })
        .then(async (r) => {
          if (r.error) { // RPC 없으면 직접 갱신
            const { data: cur } = await supabase.from("players").select("xp").eq("id", player.id).single();
            await supabase.from("players").update({ xp: (cur?.xp ?? 0) + XP.SUBMIT }).eq("id", player.id);
          }
        });
    }

    return new Response(JSON.stringify({ success: true, xp_awarded: XP.SUBMIT }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  } catch (err) {
    console.error("game-submit-picks error:", err);
    return new Response(JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }
});
```

> 참고: `increment_player_xp` RPC는 만들지 않아도 동작한다(없으면 직접 read+update fallback). 동시성 안전을 위해 Task 7 후 선택적으로 추가 가능(YAGNI — MVP는 fallback로 충분).

- [ ] **Step 2: 배포** (⚠️ 배포 — 승인 필요)

Run: `supabase functions deploy game-submit-picks`
Expected: `Deployed Function game-submit-picks`.

- [ ] **Step 3: curl 검증 (오늘 풀이 없으면 409)**

Run:
```powershell
curl -s -X POST "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1/game-submit-picks" -H "Content-Type: application/json" -H "apikey: <ANON>" -H "Authorization: Bearer <ANON>" -d '{\"device_id\":\"test-device-001\",\"picks\":[{\"ticker\":\"NVDA\",\"direction\":\"long\"}]}'
```
Expected: `{"success":false,"error":"정확히 3개를 선택해야 합니다"}` (3개 검증). 풀이 없으면 3개라도 `오늘의 종목이 아직 준비되지 않았습니다`. (정상 제출은 Task 6에서 풀 생성 후 Task 8 통합테스트로 확인)

- [ ] **Step 4: Commit**

```bash
git add supabase/functions/game-submit-picks/index.ts
git commit -m "feat(game): add game-submit-picks edge function (exactly 3 picks + submit XP)"
```

---

## Task 5: game-leaderboard Edge Function (안전 컬럼만)

**Files:**
- Create: `supabase/functions/game-leaderboard/index.ts`

- [ ] **Step 1: 함수 작성**

```ts
// supabase/functions/game-leaderboard/index.ts
// GET ?type=return|xp&limit=20 → 상위 플레이어(안전 컬럼만)
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const url = new URL(req.url);
    const type = url.searchParams.get("type") === "xp" ? "xp" : "return";
    const limit = Math.min(parseInt(url.searchParams.get("limit") ?? "20", 10) || 20, 100);
    const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

    const orderCol = type === "xp" ? "xp" : "capital";
    const { data, error } = await supabase.from("players")
      .select("display_name, level, xp, capital")
      .order(orderCol, { ascending: false }).limit(limit);
    if (error) throw error;

    const rows = (data ?? []).map((p, i) => ({
      rank: i + 1,
      display_name: p.display_name,
      level: p.level,
      xp: p.xp,
      capital: p.capital,
      return_pct: Math.round(((Number(p.capital) - 100000) / 100000) * 10000) / 100,
    }));

    return new Response(JSON.stringify({ success: true, type, rows }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  } catch (err) {
    console.error("game-leaderboard error:", err);
    return new Response(JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }
});
```

- [ ] **Step 2: 배포** (⚠️ 승인 필요)

Run: `supabase functions deploy game-leaderboard`
Expected: `Deployed Function game-leaderboard`.

- [ ] **Step 3: curl 검증**

Run:
```powershell
curl -s "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1/game-leaderboard?type=return&limit=5" -H "apikey: <ANON>" -H "Authorization: Bearer <ANON>"
```
Expected: `{"success":true,"type":"return","rows":[{"rank":1,...}]}` (Task 3에서 만든 test-device-001 포함, return_pct 0).

- [ ] **Step 4: Commit**

```bash
git add supabase/functions/game-leaderboard/index.ts
git commit -m "feat(game): add game-leaderboard edge function"
```

---

## Task 6: game-generate-pool Edge Function (오늘 풀 + 라이벌 + AI 콜)

**Files:**
- Create: `supabase/functions/game-generate-pool/index.ts`

- [ ] **Step 1: 함수 작성**

```ts
// supabase/functions/game-generate-pool/index.ts
// POST (cron) — 오늘 6종목 풀 생성, entry 시세 채움, 라이벌 AI 선정, AI 6콜 생성.
// 멱등: 이미 오늘 풀이 있으면 종목 생성은 건너뛰고 누락 보강만.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};
const todayUtc = () => new Date().toISOString().slice(0, 10);

// MVP 큐레이션: US 대형 유동성 종목 풀(여기서 6개 선택). 추후 자동 트렌딩으로 교체 가능.
const US_UNIVERSE = ["NVDA","AAPL","TSLA","MSFT","META","GOOGL","AMZN","AMD","COIN","PLTR","NFLX","AVGO"];

function pickSix(seed: number): string[] {
  // 날짜 기반 결정적 셔플(매일 다른 6개)
  const arr = [...US_UNIVERSE];
  for (let i = arr.length - 1; i > 0; i--) {
    seed = (seed * 9301 + 49297) % 233280;
    const j = Math.floor((seed / 233280) * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr.slice(0, 6);
}

async function getPrice(supabaseUrl: string, anonKey: string, ticker: string): Promise<number | null> {
  try {
    const res = await fetch(`${supabaseUrl}/functions/v1/get-price?ticker=${encodeURIComponent(ticker)}`,
      { headers: { apikey: anonKey, Authorization: `Bearer ${anonKey}` } });
    const data = await res.json();
    return typeof data.price === "number" ? data.price : null;
  } catch (_) { return null; }
}

// 라이벌 AI에게 6종목 directional call(롱/숏)을 받음. 실패 시 null(비치명적).
async function getAiCalls(tickers: { ticker: string; entry: number }[]): Promise<Record<string, "long" | "short"> | null> {
  const groqKey = Deno.env.get("GROQ_API_KEY");
  if (!groqKey) return null;
  const list = tickers.map((t) => `${t.ticker} @ $${t.entry}`).join(", ");
  const prompt = `You are a stock trader. For each ticker, decide LONG or SHORT for the next trading day based on the price.
Tickers: ${list}.
Respond ONLY as compact JSON mapping ticker to "long" or "short". Example: {"NVDA":"long","AAPL":"short"}`;
  try {
    const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: { Authorization: `Bearer ${groqKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({ model: "llama-3.3-70b-versatile", temperature: 0.4, max_tokens: 200,
        messages: [{ role: "user", content: prompt }] }),
    });
    const data = await res.json();
    const raw = data?.choices?.[0]?.message?.content ?? "";
    const clean = raw.replace(/```json/g, "").replace(/```/g, "").trim();
    const parsed = JSON.parse(clean);
    const out: Record<string, "long" | "short"> = {};
    for (const t of tickers) {
      const v = String(parsed[t.ticker] ?? "").toLowerCase();
      out[t.ticker] = v === "short" ? "short" : "long";
    }
    return out;
  } catch (_) { return null; }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? serviceKey;
    const supabase = createClient(supabaseUrl, serviceKey);
    const today = todayUtc();

    // 멱등: 이미 오늘 풀 존재?
    const { data: existing } = await supabase.from("game_ticker_pool").select("ticker, entry_price").eq("trade_date", today);
    let tickers: string[];
    if (existing && existing.length > 0) {
      tickers = existing.map((r) => r.ticker);
    } else {
      const seed = parseInt(today.replace(/-/g, ""), 10);
      tickers = pickSix(seed);
      const rows = tickers.map((t) => ({ trade_date: today, ticker: t, market: "US", sector: "US" }));
      const { error } = await supabase.from("game_ticker_pool").insert(rows);
      if (error) throw error;
    }

    // entry 시세 채우기(누락분만)
    const withEntry: { ticker: string; entry: number }[] = [];
    for (const t of tickers) {
      const { data: row } = await supabase.from("game_ticker_pool")
        .select("entry_price").eq("trade_date", today).eq("ticker", t).single();
      let entry = row?.entry_price ?? null;
      if (entry == null) {
        entry = await getPrice(supabaseUrl, anonKey, t);
        if (entry != null) {
          await supabase.from("game_ticker_pool")
            .update({ entry_price: entry, entry_price_at: new Date().toISOString(), price_source: "get-price" })
            .eq("trade_date", today).eq("ticker", t);
        }
      }
      if (entry != null) withEntry.push({ ticker: t, entry: Number(entry) });
    }

    // 라이벌 선정(없으면): agents에서 날짜 기반 로테이션
    let { data: rival } = await supabase.from("game_daily_rival").select("agent_id").eq("trade_date", today).maybeSingle();
    if (!rival) {
      const { data: agents } = await supabase.from("agents").select("id").order("created_at", { ascending: true }).limit(20);
      if (agents && agents.length > 0) {
        const idx = parseInt(today.replace(/-/g, ""), 10) % agents.length;
        const agentId = agents[idx].id;
        await supabase.from("game_daily_rival").insert({ trade_date: today, agent_id: agentId });
        rival = { agent_id: agentId };
      }
    }

    // AI 콜 생성(라이벌 picks 없으면): 비치명적
    if (rival) {
      const { count: aiCount } = await supabase.from("game_ai_pick")
        .select("id", { count: "exact", head: true }).eq("trade_date", today).eq("agent_id", rival.agent_id);
      if ((aiCount ?? 0) === 0 && withEntry.length > 0) {
        const calls = await getAiCalls(withEntry);
        const aiRows = withEntry.map((t) => ({
          agent_id: rival!.agent_id, trade_date: today, ticker: t.ticker,
          direction: calls ? calls[t.ticker] : (Math.random() < 0.5 ? "long" : "short"),
        }));
        await supabase.from("game_ai_pick").insert(aiRows);
      }
    }

    return new Response(JSON.stringify({ success: true, trade_date: today, tickers, priced: withEntry.length, rival: rival?.agent_id ?? null }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  } catch (err) {
    console.error("game-generate-pool error:", err);
    return new Response(JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }
});
```

- [ ] **Step 2: Groq 키를 함수 시크릿으로 설정** (⚠️ 승인 필요)

Run: `supabase secrets set GROQ_API_KEY=<기존 .env의 GROQ_API_KEY 값>`
Expected: `Finished supabase secrets set`. (키 없으면 AI 콜이 random fallback — 동작은 함)

- [ ] **Step 3: 배포** (⚠️ 승인 필요)

Run: `supabase functions deploy game-generate-pool`
Expected: `Deployed Function game-generate-pool`.

- [ ] **Step 4: curl 검증**

Run:
```powershell
curl -s -X POST "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1/game-generate-pool" -H "apikey: <ANON>" -H "Authorization: Bearer <ANON>"
```
Expected: `{"success":true,"trade_date":"YYYY-MM-DD","tickers":[6개],"priced":6,"rival":"<uuid>"}`. 재실행해도 같은 6종목(멱등). PostgREST로 풀 확인:
```powershell
curl -s "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1/../rest/v1/game_ticker_pool?trade_date=eq.TODAY&select=ticker,entry_price" -H "apikey: <ANON>"
```

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/game-generate-pool/index.ts
git commit -m "feat(game): add game-generate-pool with AI rival directional calls"
```

---

## Task 7: game-resolve Edge Function (판정·집계·XP·레벨·스트릭, 멱등)

**Files:**
- Create: `supabase/functions/game-resolve/index.ts`

- [ ] **Step 1: 함수 작성**

```ts
// supabase/functions/game-resolve/index.ts
// POST (cron) — 미판정 과거 풀(trade_date < 오늘)을 exit 시세로 판정.
// 픽/AI콜 판정 → 플레이어 일일집계(game_daily_result) → XP/레벨/스트릭/자산 갱신. 멱등.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { avg, computeReturnPct, isCorrect, levelFromXp, nextStreak, resultXp } from "../_shared/game_logic.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};
const todayUtc = () => new Date().toISOString().slice(0, 10);

async function getPrice(supabaseUrl: string, anonKey: string, ticker: string): Promise<number | null> {
  try {
    const res = await fetch(`${supabaseUrl}/functions/v1/get-price?ticker=${encodeURIComponent(ticker)}`,
      { headers: { apikey: anonKey, Authorization: `Bearer ${anonKey}` } });
    const data = await res.json();
    return typeof data.price === "number" ? data.price : null;
  } catch (_) { return null; }
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? serviceKey;
    const supabase = createClient(supabaseUrl, serviceKey);
    const today = todayUtc();

    // 판정 대상 날짜: 미판정 + 과거
    const { data: pools } = await supabase.from("game_ticker_pool")
      .select("trade_date").eq("resolved", false).lt("trade_date", today);
    const dates = [...new Set((pools ?? []).map((r) => r.trade_date))].sort();
    const resolvedDates: string[] = [];

    for (const tradeDate of dates) {
      // 1) 풀 exit 시세 채우고 entry/exit 맵 구성
      const { data: poolRows } = await supabase.from("game_ticker_pool")
        .select("ticker, entry_price, exit_price").eq("trade_date", tradeDate);
      const priceMap: Record<string, { entry: number; exit: number }> = {};
      for (const r of poolRows ?? []) {
        if (r.entry_price == null) continue;
        let exit = r.exit_price;
        if (exit == null) {
          exit = await getPrice(supabaseUrl, anonKey, r.ticker);
          if (exit != null) {
            await supabase.from("game_ticker_pool")
              .update({ exit_price: exit, exit_price_at: new Date().toISOString(), resolved: true })
              .eq("trade_date", tradeDate).eq("ticker", r.ticker);
          }
        }
        if (exit != null) priceMap[r.ticker] = { entry: Number(r.entry_price), exit: Number(exit) };
      }
      if (Object.keys(priceMap).length === 0) continue;

      // 2) 사용자 픽 판정
      const { data: picks } = await supabase.from("game_pick")
        .select("id, player_id, ticker, direction, resolved").eq("trade_date", tradeDate);
      for (const pk of picks ?? []) {
        if (pk.resolved) continue;
        const pm = priceMap[pk.ticker];
        if (!pm) continue;
        const ret = computeReturnPct(pk.direction, pm.entry, pm.exit);
        await supabase.from("game_pick")
          .update({ return_pct: ret, correct: isCorrect(ret), resolved: true }).eq("id", pk.id);
      }

      // 3) AI 콜 판정
      const { data: aiPicks } = await supabase.from("game_ai_pick")
        .select("id, agent_id, ticker, direction, return_pct").eq("trade_date", tradeDate);
      const aiReturnByTicker: Record<string, number> = {};
      for (const ap of aiPicks ?? []) {
        const pm = priceMap[ap.ticker];
        if (!pm) continue;
        const ret = computeReturnPct(ap.direction, pm.entry, pm.exit);
        aiReturnByTicker[ap.ticker] = ret;
        if (ap.return_pct == null) {
          await supabase.from("game_ai_pick")
            .update({ return_pct: ret, correct: isCorrect(ret) }).eq("id", ap.id);
        }
      }

      // 4) 라이벌 agent_id
      const { data: rivalRow } = await supabase.from("game_daily_rival")
        .select("agent_id").eq("trade_date", tradeDate).maybeSingle();
      const rivalAgentId = rivalRow?.agent_id ?? null;

      // 직전 풀 날짜(스트릭 판정용)
      const { data: prevPool } = await supabase.from("game_ticker_pool")
        .select("trade_date").lt("trade_date", tradeDate).order("trade_date", { ascending: false }).limit(1).maybeSingle();
      const prevTradeDate = prevPool?.trade_date ?? null;

      // 5) 플레이어별 집계
      const picksByPlayer: Record<string, { ticker: string; direction: string }[]> = {};
      const { data: allPicks } = await supabase.from("game_pick")
        .select("player_id, ticker, direction").eq("trade_date", tradeDate);
      for (const p of allPicks ?? []) {
        (picksByPlayer[p.player_id] ??= []).push({ ticker: p.ticker, direction: p.direction });
      }

      for (const [playerId, plist] of Object.entries(picksByPlayer)) {
        // 멱등: 이미 결과 있으면 skip
        const { data: existed } = await supabase.from("game_daily_result")
          .select("id").eq("player_id", playerId).eq("trade_date", tradeDate).maybeSingle();
        if (existed) continue;

        const userReturns = plist.map((p) => {
          const pm = priceMap[p.ticker];
          return pm ? computeReturnPct(p.direction as "long" | "short", pm.entry, pm.exit) : 0;
        });
        const userAvg = avg(userReturns);
        const correctCount = userReturns.filter(isCorrect).length;
        const rivalReturns = plist.map((p) => aiReturnByTicker[p.ticker]).filter((x) => x != null) as number[];
        const rivalAvg = rivalReturns.length ? avg(rivalReturns) : null;
        const beatAi = rivalAvg != null && userAvg > rivalAvg;

        // 스트릭: 직전 풀 날짜에 결과가 있었나
        let playedPrev = false;
        if (prevTradeDate) {
          const { data: prevRes } = await supabase.from("game_daily_result")
            .select("id").eq("player_id", playerId).eq("trade_date", prevTradeDate).maybeSingle();
          playedPrev = !!prevRes;
        }
        const { data: player } = await supabase.from("players")
          .select("xp, capital, streak_current, streak_best").eq("id", playerId).single();
        const newStreak = nextStreak(player!.streak_current, playedPrev);
        const { total: xpEarned, breakdown } = resultXp({ correctCount, beatAi, newStreak });

        const capitalBefore = Number(player!.capital);
        const capitalAfter = Math.round(capitalBefore * (1 + userAvg / 100) * 100) / 100;

        // 일일 결과 insert (멱등 키 UNIQUE(player_id,trade_date))
        await supabase.from("game_daily_result").insert({
          player_id: playerId, trade_date: tradeDate, picks_count: plist.length,
          avg_return_pct: Math.round(userAvg * 100) / 100, correct_count: correctCount,
          win_rate_daily: Math.round((correctCount / plist.length) * 10000) / 100,
          capital_before: capitalBefore, capital_after: capitalAfter, xp_earned: xpEarned,
          beat_ai: beatAi, ai_agent_id: rivalAgentId, ai_avg_return_pct: rivalAvg,
        });

        // XP ledger (멱등 UNIQUE(player_id,trade_date,reason))
        for (const b of breakdown) {
          await supabase.from("game_xp_ledger")
            .insert({ player_id: playerId, trade_date: tradeDate, reason: b.reason, xp_delta: b.xp });
        }

        // 플레이어 갱신
        const newXp = player!.xp + xpEarned;
        await supabase.from("players").update({
          xp: newXp, level: levelFromXp(newXp), capital: capitalAfter,
          streak_current: newStreak, streak_best: Math.max(player!.streak_best, newStreak),
          last_played_date: tradeDate,
        }).eq("id", playerId);
      }
      resolvedDates.push(tradeDate);
    }

    return new Response(JSON.stringify({ success: true, resolved_dates: resolvedDates }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  } catch (err) {
    console.error("game-resolve error:", err);
    return new Response(JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }
});
```

- [ ] **Step 2: 배포** (⚠️ 승인 필요)

Run: `supabase functions deploy game-resolve`
Expected: `Deployed Function game-resolve`.

- [ ] **Step 3: 멱등성 검증 (빈 상태에서 2회 호출)**

Run (2회):
```powershell
curl -s -X POST "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1/game-resolve" -H "apikey: <ANON>" -H "Authorization: Bearer <ANON>"
```
Expected: 두 번 다 `{"success":true,"resolved_dates":[...]}`. 같은 날짜가 중복 집계되지 않음(daily_result UNIQUE). 실제 판정값 검증은 Task 8 통합테스트.

- [ ] **Step 4: Commit**

```bash
git add supabase/functions/game-resolve/index.ts
git commit -m "feat(game): add game-resolve (scoring, aggregation, XP/level/streak, idempotent)"
```

---

## Task 8: 스케줄링 + End-to-End 통합 검증

**Files:**
- Create: `scripts/game_schedule.ps1`

- [ ] **Step 1: 스케줄 스크립트 작성**

```powershell
# scripts/game_schedule.ps1
# 게임 일일 트리거. Windows 작업 스케줄러에 2개 등록 권장:
#   - 풀 생성: US 장 마감 직후 (한국시간 평일 06:10 KST 경 = 미 동부 16:10 ET 후)
#   - 판정:    다음 US 장 마감 직후 (다음 평일 06:10 KST)
param([ValidateSet("pool","resolve")] [string]$Action)
$BASE = "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1"
$ANON = $env:SUPABASE_ANON_KEY
if (-not $ANON) { Write-Error "SUPABASE_ANON_KEY 환경변수 필요"; exit 1 }
$headers = @{ "apikey" = $ANON; "Authorization" = "Bearer $ANON" }
$fn = if ($Action -eq "pool") { "game-generate-pool" } else { "game-resolve" }
$resp = Invoke-RestMethod -Method Post -Uri "$BASE/$fn" -Headers $headers
$resp | ConvertTo-Json -Depth 5
```

> 스케줄 등록(수동, 1회): 작업 스케줄러에서
> `powershell.exe -File C:\Users\amire\AI\stockmolt\scripts\game_schedule.ps1 -Action pool` (장 마감 후),
> `... -Action resolve` (다음 장 마감 후). 또는 Supabase pg_cron으로 이전 가능(Phase 1.5 견고화).

- [ ] **Step 2: End-to-End 통합 검증 (수동, 순서대로)**

Run 순서 (`<ANON>` 치환):
```powershell
# (1) 플레이어 생성
curl -s -X POST "$BASE/game-state" -H "Content-Type: application/json" -H "apikey: <ANON>" -H "Authorization: Bearer <ANON>" -d '{\"device_id\":\"e2e-001\"}'
# (2) 오늘 풀 생성
curl -s -X POST "$BASE/game-generate-pool" -H "apikey: <ANON>" -H "Authorization: Bearer <ANON>"
# → 응답의 tickers 6개 중 3개를 골라 (3)에 사용
# (3) 3픽 제출 (TICK1/2/3을 실제 종목으로)
curl -s -X POST "$BASE/game-submit-picks" -H "Content-Type: application/json" -H "apikey: <ANON>" -H "Authorization: Bearer <ANON>" -d '{\"device_id\":\"e2e-001\",\"picks\":[{\"ticker\":\"TICK1\",\"direction\":\"long\"},{\"ticker\":\"TICK2\",\"direction\":\"short\"},{\"ticker\":\"TICK3\",\"direction\":\"long\"}]}'
# (4) 상태 확인 — submitted_today=true, xp 50 반영
curl -s -X POST "$BASE/game-state" -H "Content-Type: application/json" -H "apikey: <ANON>" -H "Authorization: Bearer <ANON>" -d '{\"device_id\":\"e2e-001\"}'
```
Expected:
- (1) `success:true`, player level 1 / xp 0
- (2) `success:true`, tickers 6개, priced 6, rival uuid
- (3) `success:true, xp_awarded:50`
- (4) `submitted_today:true`, player.xp = 50

> 판정(game-resolve)은 풀의 trade_date가 **과거가 되어야**(다음 날) 동작한다. 통합 판정 검증은 다음 거래일에 `-Action resolve` 실행 후 `game-state`의 `last_result`가 채워지는지로 확인(avg_return_pct·capital_after·beat_ai·xp_earned).

- [ ] **Step 3: Commit**

```bash
git add scripts/game_schedule.ps1
git commit -m "feat(game): add daily schedule trigger script + e2e verification"
```

---

## Self-Review (작성자 점검 결과)

**Spec 커버리지:**
- 두 화폐(XP 단조↑ / 자산 변동) → Task 2(XP/레벨), Task 4(제출 XP), Task 7(결과 XP·자산) ✓
- 6종목 중 정확히 3개 → Task 4 검증 ✓
- AI 라이벌 제출 전 확정 + 동일 종목 비교 + directional call → Task 6(라이벌/AI콜), Task 7(동일 종목 rivalAvg, beat_ai) ✓
- close-to-close 판정 → Task 6(entry), Task 7(exit) via get-price ✓
- device-id 익명 + 안전 컬럼만 노출 → Task 1 RLS, Task 3/5 ✓
- daily_player_result / xp_ledger / 풀 가격필드 → Task 1, Task 7 ✓
- 비용 0(Groq 무료, 하루 1회) → Task 6 ✓
- 멱등 판정 → Task 7 ✓

**미커버(의도적, Plan 2/후속):** 프론트 게임 탭(전체), 이메일 claim 실제 인증, 자체 게임 이벤트(GA) 계측, 레벨업 연출 — 모두 Plan 2 또는 Phase 1.5.

**Placeholder 스캔:** `<ANON>`/`<uuid>`/`TICK1` 등은 실행 시 치환값(플레이스홀더 아님, 런타임 값). 코드 내 미정의 참조 없음.

**타입 일관성:** `game_logic.ts`의 시그니처(`computeReturnPct(direction, entry, exit)`, `resultXp({correctCount,beatAi,newStreak})`, `nextStreak(prev, played)`)가 Task 7 호출부와 일치 ✓.

---

## 알려진 한계 / 후속(Plan 2·Phase 1.5)
- `get-price`는 "현재가"라 close-to-close 정확도는 cron 실행 시각에 의존(장 마감 직후 실행 전제). 휴장일이면 entry≈exit로 변동 0 처리됨(허용).
- 동시 제출 XP 갱신은 read+update fallback이라 극단적 동시성에서 경쟁 가능 → 필요 시 `increment_player_xp` RPC 추가.
- 스케줄이 지크님 PC(작업 스케줄러) 의존 → Supabase pg_cron 이전이 견고화 경로.

# Seasons & Prestige (Phase 2a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a cron-free seasonal XP leaderboard (derived from `game_xp_ledger`) plus an inline Lv.10 "Legend" prestige badge, without altering live tables.

**Architecture:** New `game_seasons` + `game_prestige` tables and two read RPCs (migration `005`). `game-leaderboard` gains a season branch (`type=xp` → current-season ledger sum via RPC). `game-resolve` awards a prestige row when a player crosses to Lv.10 in a season. `game-state` returns the player's prestige + current season. Frontend relabels the XP board to "Season", shows a countdown, and renders prestige trophies.

**Tech Stack:** Postgres (Supabase) SQL + RPC, Deno edge functions (TypeScript), vanilla JS/CSS in `index.html`, Cloudflare Pages for the frontend.

**Spec:** `docs/superpowers/specs/2026-06-17-seasons-prestige-phase2a-design.md`

---

## Branch & deploy reality (read first)

- **Backend** (migration + 3 edge functions) lives on branch `feat/game-mvp-backend`.
- **Frontend** (`index.html`) lives on `main` (live via Cloudflare Pages on push).
- Work each side in its own isolated worktree on a non-live branch. Commit nothing to `main` directly.
- **There are no automated tests for SQL/edge functions here** (the Deno tests only cover `game_logic.ts` pure functions). Verification = SQL `SELECT` checks + live `curl` smoke tests. Be honest: do not claim "tested" without these.
- **Three APPROVAL GATES** (each a live change, needs 지크님's go): applying the DB migration, deploying edge functions, pushing the frontend.
- Migration files in the repo stop at `004`, but the live DB has later ad-hoc SQL. So `005` must be **run against the live DB** (Supabase Dashboard → SQL Editor, or `psql` with the connection string) — committing the file alone does nothing.

## Setup: worktrees

- [ ] **Step 1: Backend worktree**

```
git -C c:\Users\amire\AI\stockmolt worktree add "c:\Users\amire\AI\stockmolt-wt-backend" feat/game-mvp-backend
```

- [ ] **Step 2: Frontend worktree**

```
git -C c:\Users\amire\AI\stockmolt worktree add -b feat/seasons-frontend "c:\Users\amire\AI\stockmolt-wt-frontend" main
```

---

## Task 1: Migration `005_seasons.sql` (tables + RPCs)

**Files:**
- Create: `supabase/functions/../migrations/005_seasons.sql` → exact path `supabase/migrations/005_seasons.sql` (in the backend worktree)

- [ ] **Step 1: Create the migration file**

Create `c:\Users\amire\AI\stockmolt-wt-backend\supabase\migrations\005_seasons.sql` with:

```sql
-- supabase/migrations/005_seasons.sql
-- Phase 2a: seasons + prestige. Season XP is DERIVED from game_xp_ledger (no players change, no cron).

-- 1) seasons config
CREATE TABLE IF NOT EXISTS game_seasons (
  season_no   int  PRIMARY KEY,
  name        text NOT NULL,
  start_date  date NOT NULL,
  end_date    date NOT NULL     -- inclusive
);

INSERT INTO game_seasons (season_no, name, start_date, end_date)
VALUES (1, 'Season 1', '2026-06-17', '2026-08-16')
ON CONFLICT (season_no) DO NOTHING;

-- 2) prestige badges (one row = permanent "S{n} Legend")
CREATE TABLE IF NOT EXISTS game_prestige (
  player_id   uuid NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  season_no   int  NOT NULL REFERENCES game_seasons(season_no),
  awarded_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (player_id, season_no)
);

-- 3) index so the season-window aggregation stays cheap
CREATE INDEX IF NOT EXISTS idx_xp_ledger_trade_date ON game_xp_ledger(trade_date);

-- 4) RLS: edge-function (service-role) only; no anon policy
ALTER TABLE game_seasons  ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_prestige ENABLE ROW LEVEL SECURITY;

-- 5) RPC: season leaderboard (top N by ledger sum in the window)
CREATE OR REPLACE FUNCTION get_season_leaderboard(p_start date, p_end date, p_limit int)
RETURNS TABLE(display_name text, level int, season_xp bigint)
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  SELECT p.display_name, p.level, COALESCE(SUM(l.xp_delta),0)::bigint AS season_xp
  FROM game_xp_ledger l JOIN players p ON p.id = l.player_id
  WHERE l.trade_date BETWEEN p_start AND p_end
  GROUP BY p.id, p.display_name, p.level
  HAVING SUM(l.xp_delta) > 0
  ORDER BY season_xp DESC
  LIMIT p_limit;
$$;

-- 6) RPC: a viewer's own season xp + rank (pin-my-rank)
CREATE OR REPLACE FUNCTION get_season_my_rank(p_start date, p_end date, p_device text)
RETURNS TABLE(display_name text, season_xp bigint, rank int)
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  WITH sums AS (
    SELECT p.id, p.display_name, p.device_id, COALESCE(SUM(l.xp_delta),0)::bigint AS sx
    FROM players p JOIN game_xp_ledger l ON l.player_id = p.id
    WHERE l.trade_date BETWEEN p_start AND p_end
    GROUP BY p.id, p.display_name, p.device_id
  )
  SELECT s.display_name, s.sx AS season_xp,
         ((SELECT COUNT(*) FROM sums s2 WHERE s2.sx > s.sx)::int + 1) AS rank
  FROM sums s
  WHERE s.device_id = p_device AND s.sx > 0;
$$;

-- 7) only edge functions (service-role) may call the RPCs
REVOKE EXECUTE ON FUNCTION get_season_leaderboard(date,date,int) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION get_season_my_rank(date,date,text)    FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION get_season_leaderboard(date,date,int) TO service_role;
GRANT  EXECUTE ON FUNCTION get_season_my_rank(date,date,text)    TO service_role;
```

- [ ] **Step 2: Commit the file**

```
git -C "c:\Users\amire\AI\stockmolt-wt-backend" add supabase/migrations/005_seasons.sql
git -C "c:\Users\amire\AI\stockmolt-wt-backend" commit -m "feat(game-be): 005 seasons + prestige tables and season-leaderboard RPCs"
```

---

## Task 2: Apply migration to live DB — APPROVAL GATE

The RPCs/tables must exist before the edge functions that call them deploy.

- [ ] **Step 1: Get 지크님's approval to run DDL on the live DB.**

- [ ] **Step 2: Apply the SQL.** Preferred: Supabase Dashboard → SQL Editor → paste the entire contents of `005_seasons.sql` → Run. (Alternative if the DB connection string is available: `psql "<connection-string>" -f supabase/migrations/005_seasons.sql`.)

- [ ] **Step 3: Verify objects exist.** In the SQL Editor run:
```sql
SELECT * FROM game_seasons;
SELECT to_regclass('public.game_prestige') AS prestige_table;
SELECT * FROM get_season_leaderboard('2026-06-17','2026-08-16',5);
```
Expected: one Season 1 row; `prestige_table` = `game_prestige`; the leaderboard query returns rows (or zero rows with no error if no ledger entries in-window yet).

---

## Task 3: `game-leaderboard` — season branch

**Files:**
- Modify (full rewrite): `supabase/functions/game-leaderboard/index.ts` (backend worktree)

- [ ] **Step 1: Replace the entire file** with:

```ts
// supabase/functions/game-leaderboard/index.ts
// GET ?type=return|xp&limit=20&device_id=...
//   return → lifetime capital (players + AI agents merged), pin-my-rank
//   xp     → CURRENT SEASON xp (derived from game_xp_ledger via RPC), pin-my-rank
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

function todayUtc(): string { return new Date().toISOString().slice(0, 10); }

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const url = new URL(req.url);
    const type = url.searchParams.get("type") === "xp" ? "xp" : "return";
    const limit = Math.min(parseInt(url.searchParams.get("limit") ?? "20", 10) || 20, 100);
    const deviceId = url.searchParams.get("device_id");
    const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const retPct = (cap: number) => Math.round(((cap - 100000) / 100000) * 10000) / 100;

    // ===== SEASON XP BOARD =====
    if (type === "xp") {
      const today = todayUtc();
      const { data: seas } = await supabase.from("game_seasons")
        .select("season_no, name, start_date, end_date")
        .lte("start_date", today).gte("end_date", today).maybeSingle();

      if (seas) {
        const { data: lb } = await supabase.rpc("get_season_leaderboard",
          { p_start: seas.start_date, p_end: seas.end_date, p_limit: limit });
        const rows = (lb ?? []).map((r: any, i: number) => ({
          rank: i + 1, is_ai: false, display_name: r.display_name, level: r.level,
          xp: Number(r.season_xp), capital: 0, return_pct: 0,
        }));
        let me = null;
        if (deviceId) {
          const { data: mine } = await supabase.rpc("get_season_my_rank",
            { p_start: seas.start_date, p_end: seas.end_date, p_device: deviceId });
          const m = (mine ?? [])[0];
          if (m) me = { rank: Number(m.rank), display_name: m.display_name, xp: Number(m.season_xp), capital: 0, return_pct: 0, is_ai: false };
        }
        return new Response(JSON.stringify({ success: true, type, rows, ai_total: 0, me,
          season: { season_no: seas.season_no, name: seas.name, end_date: seas.end_date } }),
          { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
      }
      // fallback: no current season → lifetime xp
      const { data } = await supabase.from("players")
        .select("display_name, level, xp, capital").gt("xp", 0)
        .order("xp", { ascending: false }).limit(limit);
      const rows = (data ?? []).map((p: any, i: number) => ({
        rank: i + 1, is_ai: false, display_name: p.display_name, level: p.level,
        xp: p.xp, capital: Number(p.capital), return_pct: retPct(Number(p.capital)),
      }));
      return new Response(JSON.stringify({ success: true, type, rows, ai_total: 0, me: null, season: null }),
        { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
    }

    // ===== RETURN BOARD (unchanged behavior) =====
    const { data, error } = await supabase.from("players")
      .select("display_name, level, xp, capital")
      .gt("xp", 0)
      .order("capital", { ascending: false }).limit(limit);
    if (error) throw error;

    type LbRow = { is_ai: boolean; display_name: string; level: number | null; xp: number | null; capital: number; return_pct: number };
    let merged: LbRow[] = (data ?? []).map((p) => ({
      is_ai: false, display_name: p.display_name, level: p.level, xp: p.xp,
      capital: Number(p.capital), return_pct: retPct(Number(p.capital)),
    }));

    const { count: rosterCount } = await supabase.from("agents")
      .select("id", { count: "exact", head: true }).or("game_roster.eq.true,game_external.eq.true");
    const aiTotal = rosterCount ?? 0;
    const { data: ags } = await supabase.from("agents")
      .select("name, game_capital").or("game_roster.eq.true,game_external.eq.true")
      .order("game_capital", { ascending: false }).limit(limit);
    const aiRows: LbRow[] = (ags ?? []).map((a) => ({
      is_ai: true, display_name: a.name, level: null, xp: null,
      capital: Number(a.game_capital), return_pct: retPct(Number(a.game_capital)),
    }));
    merged = merged.concat(aiRows).sort((x, y) => y.capital - x.capital).slice(0, limit);

    const rows = merged.map((p, i) => ({ rank: i + 1, ...p }));

    let me = null;
    if (deviceId) {
      const { data: meP } = await supabase.from("players")
        .select("display_name, capital, xp").eq("device_id", deviceId).maybeSingle();
      if (meP && Number(meP.xp) > 0) {
        const cap = Number(meP.capital);
        const { count: betterPlayers } = await supabase.from("players")
          .select("id", { count: "exact", head: true }).gt("xp", 0).gt("capital", cap);
        const { count: betterAgents } = await supabase.from("agents")
          .select("id", { count: "exact", head: true }).or("game_roster.eq.true,game_external.eq.true").gt("game_capital", cap);
        me = { rank: (betterPlayers ?? 0) + (betterAgents ?? 0) + 1, display_name: meP.display_name, capital: cap, return_pct: retPct(cap), is_ai: false };
      }
    }

    return new Response(JSON.stringify({ success: true, type, rows, ai_total: aiTotal, me, season: null }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  } catch (err) {
    console.error("game-leaderboard error:", err);
    return new Response(JSON.stringify({ success: false, error: "Internal server error" }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }
});
```

- [ ] **Step 2: Commit**

```
git -C "c:\Users\amire\AI\stockmolt-wt-backend" add supabase/functions/game-leaderboard/index.ts
git -C "c:\Users\amire\AI\stockmolt-wt-backend" commit -m "feat(game-be): season xp leaderboard branch (ledger-derived, pin-my-rank)"
```

---

## Task 4: `game-resolve` — inline prestige award

**Files:**
- Modify: `supabase/functions/game-resolve/index.ts` (backend worktree)

- [ ] **Step 1: Insert the prestige block after the players update.**

Find this exact block (inside the per-player settle loop):
```ts
        const newXp = player!.xp + xpEarned;
        await supabase.from("players").update({
          xp: newXp, level: levelFromXp(newXp), capital: capitalAfter,
          streak_current: newStreak, streak_best: Math.max(player!.streak_best, newStreak),
          last_played_date: tradeDate,
        }).eq("id", playerId);
```
Immediately AFTER it, insert:
```ts
        // Phase 2a: one-time "Legend" prestige when crossing to Lv.10 within a season
        try {
          if (levelFromXp(player!.xp) < 10 && levelFromXp(newXp) === 10) {
            const { data: season } = await supabase.from("game_seasons")
              .select("season_no").lte("start_date", tradeDate).gte("end_date", tradeDate).maybeSingle();
            if (season) {
              await supabase.from("game_prestige")
                .upsert({ player_id: playerId, season_no: season.season_no }, { onConflict: "player_id,season_no", ignoreDuplicates: true });
            }
          }
        } catch (e) { console.error("prestige award error", playerId, e); }
```
(`levelFromXp` is already imported; `player`, `newXp`, `playerId`, `tradeDate` are all in scope.)

- [ ] **Step 2: Commit**

```
git -C "c:\Users\amire\AI\stockmolt-wt-backend" add supabase/functions/game-resolve/index.ts
git -C "c:\Users\amire\AI\stockmolt-wt-backend" commit -m "feat(game-be): award Lv.10 'Legend' prestige inline at resolve (idempotent)"
```

---

## Task 5: `game-state` — prestige + current season

**Files:**
- Modify: `supabase/functions/game-state/index.ts` (backend worktree)

- [ ] **Step 1: Add the season + prestige lookups.**

Find this block:
```ts
    const safePlayer = {
      id: player.id, display_name: player.display_name, level: player.level, xp: player.xp,
      streak_current: player.streak_current, streak_best: player.streak_best,
      capital: player.capital, claimed: player.claimed,
    };
```
Immediately BEFORE it, insert:
```ts
    const { data: season } = await supabase.from("game_seasons")
      .select("season_no, name, end_date").lte("start_date", today).gte("end_date", today).maybeSingle();
    let current_season = null;
    if (season) {
      const ends = Math.max(0, Math.ceil(
        (new Date(season.end_date + "T00:00:00Z").getTime() - new Date(today + "T00:00:00Z").getTime()) / 86400000));
      current_season = { season_no: season.season_no, name: season.name, end_date: season.end_date, ends_in_days: ends };
    }
    const { data: prestigeRows } = await supabase.from("game_prestige")
      .select("season_no").eq("player_id", player.id).order("season_no", { ascending: true });
    const prestige = (prestigeRows ?? []).map((r: any) => r.season_no);
```
Then change `safePlayer` to include prestige — replace the block above with:
```ts
    const safePlayer = {
      id: player.id, display_name: player.display_name, level: player.level, xp: player.xp,
      streak_current: player.streak_current, streak_best: player.streak_best,
      capital: player.capital, claimed: player.claimed, prestige,
    };
```

- [ ] **Step 2: Add `current_season` to the response.**

Find:
```ts
    return new Response(JSON.stringify({
      success: true,
      player: safePlayer,
      submitted_today: (pickCount ?? 0) > 0,
      last_result: lastResult ?? null,
    }), { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
```
Replace with (add the `current_season` line):
```ts
    return new Response(JSON.stringify({
      success: true,
      player: safePlayer,
      submitted_today: (pickCount ?? 0) > 0,
      last_result: lastResult ?? null,
      current_season,
    }), { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } });
```

- [ ] **Step 3: Commit**

```
git -C "c:\Users\amire\AI\stockmolt-wt-backend" add supabase/functions/game-state/index.ts
git -C "c:\Users\amire\AI\stockmolt-wt-backend" commit -m "feat(game-be): game-state returns prestige + current_season"
```

---

## Task 6: Deploy edge functions — APPROVAL GATE

Migration (Task 2) MUST already be applied or `type=xp` will error.

- [ ] **Step 1: Get 지크님's approval.**

- [ ] **Step 2: Deploy** (from the backend worktree, env PATH refreshed):
```
supabase functions deploy game-leaderboard game-resolve game-state --project-ref oyatbvqpilvbhqpiafwp
```
Expected: all three report deployed.

- [ ] **Step 3: Live smoke (curl).**
```
curl -s "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1/game-leaderboard?type=xp&limit=5" -H "apikey: sb_publishable_8-tR6LbXU-l0qdgFmYnH-A_WxSuuBi0"
```
Expected: JSON `success:true`, `type:"xp"`, a `season` object with `season_no:1`, and `rows` (possibly empty early). No 500.

---

## Task 7: Frontend (label + season header + prestige + countdown)

**Files:**
- Modify: `index.html` (frontend worktree on `feat/seasons-frontend`)

- [ ] **Step 1: Add CSS** — after the cosmetic-ladder block (search for `@keyframes gmAuraGold`), insert:
```css
    .gm-lb-season{font-size:12px;font-weight:800;color:#e3b341;text-align:center;padding:6px 0 2px;}
    .gm-prestige{font-size:12px;color:#e3b341;font-weight:700;margin-top:3px;}
    .gm-season-cd{font-size:12px;color:#7ee3f5;font-weight:700;margin-top:6px;}
```

- [ ] **Step 2: Store the season globally.** Find the module vars near `let gmSel = {};` and add:
```js
    let gmSeason = null;     // current season (from game-state) for card countdown
```

- [ ] **Step 3: Capture season + render countdown in renderGame.** Find:
```js
      gmStartBattle(state.submitted_today);
      gmRenderCharacter(state.player, gmPlayer, state.submitted_today);
```
Replace with:
```js
      gmSeason = state.current_season || null;
      gmStartBattle(state.submitted_today);
      gmRenderCharacter(state.player, gmPlayer, state.submitted_today);
```

- [ ] **Step 4: Render prestige + countdown on the card.** In `gmRenderCharacter`, find:
```js
          +'<div class="gm-title">Lv.'+li.lvl+' · '+li.title+'</div>'
```
Replace with:
```js
          +'<div class="gm-title">Lv.'+li.lvl+' · '+li.title+'</div>'
          +((p.prestige&&p.prestige.length)?'<div class="gm-prestige">'+p.prestige.map(function(n){return '🏆 S'+n+' Legend';}).join(' ')+'</div>':'')
          +(gmSeason?'<div class="gm-season-cd">🏆 '+gmSeason.name+' · ends in '+gmSeason.ends_in_days+' day'+(gmSeason.ends_in_days===1?'':'s')+'</div>':'')
```

- [ ] **Step 5: Relabel the XP toggle button.** Find (in `gmLoadLeaderboard`):
```js
onclick="gmLoadLeaderboard(\'xp\')">⭐ XP</button>
```
Replace `⭐ XP` with `🏆 Season`:
```js
onclick="gmLoadLeaderboard(\'xp\')">🏆 Season</button>
```

- [ ] **Step 6: Season header + pin-my-rank for the XP board.** Find:
```js
        const hdr=(type==='return'&&aiTotal>0)?('<div class="gm-lb-aihdr">🤖 You\'re up against '+aiTotal+' AI trader'+(aiTotal===1?'':'s')+'</div>'):'';
        // 내 순위 핀: Return 보드에서 상위 컷 밖이면 맨 아래에 내 행 고정
        const me=d.me; let meHtml='';
        if(type==='return' && me && me.rank>rows.length){
          const mvcls=me.return_pct>=0?'gm-pos':'gm-neg';
          const mval=(me.return_pct>=0?'+':'')+me.return_pct+'%';
          meHtml='<div class="gm-lb-mediv">⋯</div><div class="gm-lbrow gm-lb-me"><span class="rk">'+me.rank+'</span><span class="nm">🧑‍💻 '+(me.display_name||'You')+' <span style="color:#8b949e;font-size:11px">YOU</span></span><span class="vl '+mvcls+'">'+mval+'</span></div>';
        }
```
Replace with:
```js
        let hdr=(type==='return'&&aiTotal>0)?('<div class="gm-lb-aihdr">🤖 You\'re up against '+aiTotal+' AI trader'+(aiTotal===1?'':'s')+'</div>'):'';
        if(type==='xp' && d.season){
          let endTxt='';
          if(d.season.end_date){ const dd=Math.max(0,Math.ceil((new Date(d.season.end_date+'T00:00:00Z')-new Date())/86400000)); endTxt=' · ends in '+dd+' day'+(dd===1?'':'s'); }
          hdr='<div class="gm-lb-season">🏆 '+(d.season.name||'Season')+endTxt+'</div>'+hdr;
        }
        // 내 순위 핀: 상위 컷 밖이면 맨 아래에 내 행 고정 (return=수익률, xp=시즌XP)
        const me=d.me; let meHtml='';
        if(me && me.rank>rows.length){
          if(type==='xp'){
            meHtml='<div class="gm-lb-mediv">⋯</div><div class="gm-lbrow gm-lb-me"><span class="rk">'+me.rank+'</span><span class="nm">🧑‍💻 '+(me.display_name||'You')+' <span style="color:#8b949e;font-size:11px">YOU</span></span><span class="vl">⭐ '+me.xp+'</span></div>';
          } else {
            const mvcls=me.return_pct>=0?'gm-pos':'gm-neg';
            const mval=(me.return_pct>=0?'+':'')+me.return_pct+'%';
            meHtml='<div class="gm-lb-mediv">⋯</div><div class="gm-lbrow gm-lb-me"><span class="rk">'+me.rank+'</span><span class="nm">🧑‍💻 '+(me.display_name||'You')+' <span style="color:#8b949e;font-size:11px">YOU</span></span><span class="vl '+mvcls+'">'+mval+'</span></div>';
          }
        }
```

- [ ] **Step 7: Commit**

```
git -C "c:\Users\amire\AI\stockmolt-wt-frontend" add index.html
git -C "c:\Users\amire\AI\stockmolt-wt-frontend" commit -m "feat(game): season leaderboard label/header, prestige trophies, season countdown"
```

- [ ] **Step 8: Browser smoke test (human).** Open `c:\Users\amire\AI\stockmolt-wt-frontend\index.html`, go to the game view, switch the leaderboard to the new "🏆 Season" tab: confirm it loads (season header shows "Season 1 · ends in N days"), no console errors. The card countdown shows "🏆 Season 1 · ends in N days". (Prestige trophies only show for Lv.10 players — likely none yet; that's fine.)

---

## Task 8: Frontend go-live — APPROVAL GATE

- [ ] **Step 1: Merge to main (no push).**
```
git -C c:\Users\amire\AI\stockmolt merge --ff-only feat/seasons-frontend
```

- [ ] **Step 2: Push (Cloudflare deploy) — REQUIRES 지크님 approval.**
```
git -C c:\Users\amire\AI\stockmolt push origin main
```

- [ ] **Step 3: Verify live.** Poll `https://stockmolt.pages.dev/` until the HTML contains `gm-lb-season`. Load the live game, open the Season board, confirm it renders.

- [ ] **Step 4: Cleanup.**
```
git -C c:\Users\amire\AI\stockmolt worktree remove --force "c:\Users\amire\AI\stockmolt-wt-backend"
git -C c:\Users\amire\AI\stockmolt worktree remove --force "c:\Users\amire\AI\stockmolt-wt-frontend"
git -C c:\Users\amire\AI\stockmolt branch -d feat/seasons-frontend
git -C c:\Users\amire\AI\stockmolt push origin feat/game-mvp-backend   # backup the backend commits (approval)
```

---

## Self-Review notes

- **Spec coverage:** game_seasons + game_prestige + index + seed → Task 1. Derived season XP RPCs → Task 1 (5,6). game-leaderboard season branch + fallback + season in response → Task 3. Inline Lv.10 prestige → Task 4. game-state prestige + current_season → Task 5. Frontend label/header/prestige/countdown → Task 7. No cron, no players change → confirmed (no task alters `players` or adds a cron). ✓
- **Placeholder scan:** none — full SQL/TS/JS provided. ✓
- **Type/name consistency:** RPC names `get_season_leaderboard` / `get_season_my_rank` match between Task 1 (definition) and Task 3 (`supabase.rpc(...)` calls). `game_prestige` columns `(player_id, season_no)` match between Task 1 (UNIQUE), Task 4 (upsert onConflict), Task 5 (select). Response field `season` (leaderboard) and `current_season` (state) are distinct and consumed correctly in Task 7 (`d.season` in `gmLoadLeaderboard`, `gmSeason`/`current_season` on the card). `me.xp` for the season board is produced in Task 3 and rendered in Task 7 step 6. ✓
- **Deploy order dependency:** Task 2 (migration) before Task 6 (functions) before Task 8 (frontend) — encoded as gates. ✓

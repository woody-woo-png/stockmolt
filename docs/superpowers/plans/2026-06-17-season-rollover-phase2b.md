# Season Rollover & Finish Rewards (Phase 2b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a season ends, the nightly `game-resolve` finalizes it — awarding a Champion (#1) and Finalists (top 10%, min-3 guard) and opening the next season — with no new scheduled job.

**Architecture:** Migration `006` adds `game_seasons.finalized`, a `game_season_award` table, and a `get_season_standings` RPC. `game-resolve` gains an idempotent finalize step after its settle loop. `game-state` returns the player's season awards. The card renders them next to the Lv.10 Legend trophy.

**Tech Stack:** Postgres/Supabase SQL + RPC, Deno edge functions, vanilla JS in `index.html`, Cloudflare Pages.

**Spec:** `docs/superpowers/specs/2026-06-17-season-rollover-phase2b-design.md`

---

## Branch & deploy reality (read first)

- Backend (migration + `game-resolve`, `game-state`) on branch `feat/game-mvp-backend` (it already contains Phase 2a). Frontend `index.html` on `main` (live).
- Work each side in its own worktree on a non-live branch; commit nothing to `main` directly.
- No automated tests for SQL/edge functions; verify via SQL `SELECT` + live `curl`.
- **Three APPROVAL GATES** (live changes, need 지크님): apply DB migration, deploy edge functions, push frontend. The migration must be **run against the live DB** (Supabase SQL Editor) — committing the file alone does nothing.

## Setup: worktrees

- [ ] **Step 1:** `git -C c:\Users\amire\AI\stockmolt worktree add "c:\Users\amire\AI\stockmolt-wt-backend" feat/game-mvp-backend`
- [ ] **Step 2:** `git -C c:\Users\amire\AI\stockmolt worktree add -b feat/rollover-frontend "c:\Users\amire\AI\stockmolt-wt-frontend" main`

---

## Task 1: Migration `006_season_rollover.sql`

**Files:** Create `supabase/migrations/006_season_rollover.sql` (backend worktree)

- [ ] **Step 1: Create the file** with:

```sql
-- supabase/migrations/006_season_rollover.sql
-- Phase 2b: season finalize + finish awards (rollover rides daily game-resolve; no new cron).

ALTER TABLE game_seasons ADD COLUMN IF NOT EXISTS finalized boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS game_season_award (
  season_no   int  NOT NULL REFERENCES game_seasons(season_no),
  player_id   uuid NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  rank        int  NOT NULL,
  tier        text NOT NULL,          -- 'champion' | 'finalist'
  awarded_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (season_no, player_id)
);
ALTER TABLE game_season_award ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION get_season_standings(p_start date, p_end date)
RETURNS TABLE(player_id uuid, season_xp bigint, rank int)
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  WITH sums AS (
    SELECT l.player_id, COALESCE(SUM(l.xp_delta),0)::bigint AS sx
    FROM game_xp_ledger l
    WHERE l.trade_date BETWEEN p_start AND p_end
    GROUP BY l.player_id
    HAVING SUM(l.xp_delta) > 0
  )
  SELECT s.player_id, s.sx AS season_xp,
         (RANK() OVER (ORDER BY s.sx DESC))::int AS rank
  FROM sums s
  ORDER BY rank;
$$;
REVOKE EXECUTE ON FUNCTION get_season_standings(date,date) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION get_season_standings(date,date) TO service_role;
```

- [ ] **Step 2: Commit**

```
git -C "c:\Users\amire\AI\stockmolt-wt-backend" add supabase/migrations/006_season_rollover.sql
git -C "c:\Users\amire\AI\stockmolt-wt-backend" commit -m "feat(game-be): 006 season finalize column + season_award table + standings RPC"
```

---

## Task 2: Apply migration to live DB — APPROVAL GATE

- [ ] **Step 1:** Get 지크님's approval.
- [ ] **Step 2:** Supabase Dashboard → SQL Editor → paste the full `006_season_rollover.sql` → Run.
- [ ] **Step 3: Verify.** Run:
```sql
SELECT season_no, finalized FROM game_seasons;
SELECT to_regclass('public.game_season_award') AS award_table;
SELECT * FROM get_season_standings('2026-06-17','2026-08-16');
```
Expected: Season 1 with `finalized = false`; `award_table` = `game_season_award`; standings query runs without error (rows or empty).

---

## Task 3: `game-resolve` — finalize step

**Files:** Modify `supabase/functions/game-resolve/index.ts` (backend worktree)

- [ ] **Step 1: Insert the finalize block** between the end of the per-`tradeDate` loop and the final response. Find this exact anchor:
```ts
      resolvedDates.push(tradeDate);
    }

    return new Response(JSON.stringify({ success: true, resolved_dates: resolvedDates }),
```
Insert the finalize block so it reads:
```ts
      resolvedDates.push(tradeDate);
    }

    // Phase 2b: finalize any ended, not-yet-finalized season (idempotent; rides this daily run)
    try {
      const nowDate = new Date().toISOString().slice(0, 10);
      const { data: ended } = await supabase.from("game_seasons")
        .select("season_no, start_date, end_date").lt("end_date", nowDate).eq("finalized", false);
      for (const s of ended ?? []) {
        try {
          const { data: standings } = await supabase.rpc("get_season_standings",
            { p_start: s.start_date, p_end: s.end_date });
          const list = standings ?? [];
          if (list.length >= 3) {
            const finalistMax = Math.max(1, Math.ceil(list.length * 0.10));
            for (const row of list) {
              if (row.rank > finalistMax) continue;
              const tier = row.rank === 1 ? "champion" : "finalist";
              await supabase.from("game_season_award")
                .upsert({ season_no: s.season_no, player_id: row.player_id, rank: row.rank, tier },
                        { onConflict: "season_no,player_id", ignoreDuplicates: true });
            }
          }
          await supabase.from("game_seasons").update({ finalized: true }).eq("season_no", s.season_no);
          const start2 = new Date(s.end_date + "T00:00:00Z"); start2.setUTCDate(start2.getUTCDate() + 1);
          const end2 = new Date(start2); end2.setUTCMonth(end2.getUTCMonth() + 2); end2.setUTCDate(end2.getUTCDate() - 1);
          const iso = (d: Date) => d.toISOString().slice(0, 10);
          await supabase.from("game_seasons")
            .upsert({ season_no: s.season_no + 1, name: "Season " + (s.season_no + 1),
                      start_date: iso(start2), end_date: iso(end2) }, { onConflict: "season_no", ignoreDuplicates: true });
        } catch (e) { console.error("season finalize error", s.season_no, e); }
      }
    } catch (e) { console.error("season finalize block error", e); }

    return new Response(JSON.stringify({ success: true, resolved_dates: resolvedDates }),
```

- [ ] **Step 2: Commit**

```
git -C "c:\Users\amire\AI\stockmolt-wt-backend" add supabase/functions/game-resolve/index.ts
git -C "c:\Users\amire\AI\stockmolt-wt-backend" commit -m "feat(game-be): finalize ended seasons + award champion/finalist + open next season"
```

---

## Task 4: `game-state` — return season awards

**Files:** Modify `supabase/functions/game-state/index.ts` (backend worktree)

- [ ] **Step 1: Add the awards lookup** after the Phase 2a prestige lines. Find:
```ts
    const { data: prestigeRows } = await supabase.from("game_prestige")
      .select("season_no").eq("player_id", player.id).order("season_no", { ascending: true });
    const prestige = (prestigeRows ?? []).map((r: any) => r.season_no);
```
Immediately AFTER, insert:
```ts
    const { data: awardRows } = await supabase.from("game_season_award")
      .select("season_no, tier").eq("player_id", player.id).order("season_no", { ascending: true });
    const season_awards = (awardRows ?? []).map((r: any) => ({ season_no: r.season_no, tier: r.tier }));
```

- [ ] **Step 2: Add `season_awards` to `safePlayer`.** Find:
```ts
      capital: player.capital, claimed: player.claimed, prestige,
    };
```
Replace with:
```ts
      capital: player.capital, claimed: player.claimed, prestige, season_awards,
    };
```

- [ ] **Step 3: Commit**

```
git -C "c:\Users\amire\AI\stockmolt-wt-backend" add supabase/functions/game-state/index.ts
git -C "c:\Users\amire\AI\stockmolt-wt-backend" commit -m "feat(game-be): game-state returns season_awards"
```

---

## Task 5: Deploy edge functions — APPROVAL GATE

Migration (Task 2) MUST be applied first.

- [ ] **Step 1:** Get 지크님's approval.
- [ ] **Step 2:** From the backend worktree (PATH refreshed):
```
supabase functions deploy game-resolve game-state --project-ref oyatbvqpilvbhqpiafwp
```
- [ ] **Step 3: Smoke.** `game-resolve` is POST-only and runs the settle batch — do NOT invoke it ad hoc just to test (it has side effects and is triggered nightly). Instead verify `game-state` is healthy:
```
curl -s -X POST "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1/game-state" -H "apikey: sb_publishable_8-tR6LbXU-l0qdgFmYnH-A_WxSuuBi0" -H "Content-Type: application/json" -d '{"device_id":"smoke-test-2b"}'
```
Expected: JSON `success:true` with a `player` object that now includes `season_awards: []` (and `prestige: []`, `current_season`). No 500. (This creates a throwaway `smoke-test-2b` player; harmless.)

---

## Task 6: Frontend — render season awards on the card

**Files:** Modify `index.html` (frontend worktree on `feat/rollover-frontend`)

- [ ] **Step 1: Add the awards line** in `gmRenderCharacter`, right after the Phase 2a prestige line. Find:
```js
          +((p.prestige&&p.prestige.length)?'<div class="gm-prestige">'+p.prestige.map(function(n){return '🏆 S'+n+' Legend';}).join(' ')+'</div>':'')
```
Immediately AFTER it, add:
```js
          +((p.season_awards&&p.season_awards.length)?'<div class="gm-prestige">'+p.season_awards.map(function(a){return (a.tier==='champion'?'🥇 S'+a.season_no+' Champion':'🏅 S'+a.season_no+' Finalist');}).join(' ')+'</div>':'')
```
(Reuses the existing `.gm-prestige` style — no new CSS.)

- [ ] **Step 2: Commit**

```
git -C "c:\Users\amire\AI\stockmolt-wt-frontend" add index.html
git -C "c:\Users\amire\AI\stockmolt-wt-frontend" commit -m "feat(game): render season champion/finalist awards on the card"
```

- [ ] **Step 3: Browser smoke test (human).** Open `c:\Users\amire\AI\stockmolt-wt-frontend\index.html`, load the game view, confirm no console errors and the card renders normally. (Award trophies only show once a season has finalized — none yet, since Season 1 ends 2026-08-16; absence is correct.)

---

## Task 7: Frontend go-live — APPROVAL GATE

- [ ] **Step 1:** `git -C c:\Users\amire\AI\stockmolt merge --ff-only feat/rollover-frontend`
- [ ] **Step 2 (REQUIRES approval):** `git -C c:\Users\amire\AI\stockmolt push origin main`
- [ ] **Step 3: Verify live.** Poll `https://stockmolt.pages.dev/` until the HTML contains `S'+a.season_no+' Champion` (i.e. the new render line is present). Load the live game; confirm it renders without errors.
- [ ] **Step 4: Cleanup.**
```
git -C c:\Users\amire\AI\stockmolt worktree remove --force "c:\Users\amire\AI\stockmolt-wt-backend"
git -C c:\Users\amire\AI\stockmolt worktree remove --force "c:\Users\amire\AI\stockmolt-wt-frontend"
git -C c:\Users\amire\AI\stockmolt branch -d feat/rollover-frontend
git -C c:\Users\amire\AI\stockmolt push origin feat/game-mvp-backend   # backup backend commits
```

---

## Self-Review notes

- **Spec coverage:** finalized column + game_season_award + standings RPC → Task 1. finalize/award/next-season logic → Task 3. game-state awards → Task 4. card render → Task 6. No new cron (rides game-resolve) → confirmed. ✓
- **Placeholder scan:** none — full SQL/TS/JS. ✓
- **Type/name consistency:** `get_season_standings` defined in Task 1, called in Task 3. `game_season_award (season_no, player_id, rank, tier)` columns match between Task 1 (table), Task 3 (upsert), Task 4 (select). Response field `season_awards` produced in Task 4 and consumed in Task 6. `tier` values `'champion'`/`'finalist'` match between Task 3 (write) and Task 6 (render). ✓
- **finalistMax logic:** `Math.max(1, ceil(n*0.10))`; rank 1 → champion, ranks 2..finalistMax → finalist; n=3→1 (champion only), n=20→2, n=100→10. Min-3 guard gates the whole award block. ✓
- **Idempotency:** `finalized` flag filters the season query; awards `upsert` ignoreDuplicates; next-season `upsert` ignoreDuplicates. Safe to run every night. ✓
- **Deploy order:** Task 2 (migration) → Task 5 (functions) → Task 7 (frontend), encoded as gates. ✓

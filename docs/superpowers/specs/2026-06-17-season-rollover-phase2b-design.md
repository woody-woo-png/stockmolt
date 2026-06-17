# Season Rollover & Finish Rewards (Phase 2b) — Design

**Date:** 2026-06-17
**Status:** Design approved, pending spec review → implementation plan
**Parent:** `2026-06-17-progression-engagement-economy-design.md` (section 2b)
**Builds on:** `2026-06-17-seasons-prestige-phase2a-design.md`

## Problem

Phase 2a shipped the seasonal leaderboard + Lv.10 Legend badge, but a season never
"ends": there is no end-of-season reward and (without a new season row) the board would
fall back to lifetime XP after Season 1's `end_date`. Phase 2b closes the loop: reward the
top finishers each season and roll the world into the next season.

## Goal

When a season ends, award the top finishers a permanent, accumulating season badge and
automatically open the next season — **without adding any new scheduled job**.

## Key decisions (locked during brainstorming)

1. **Rollover rides the existing daily `game-resolve`** (which already runs after each US
   close via Windows Task Scheduler). No new cron, no new function entry. The rollover is an
   isolated, idempotent step appended to the nightly batch.
2. **Tiered finish rewards by season XP:** rank 1 → 🥇 "Season N Champion"; ranks 2..⌈10%⌉ →
   🏅 "Season N Finalist". Scales from a tiny founding base to a large one.
3. **Minimum-participants guard:** award only if ≥ 3 players have season_xp > 0 (avoids
   "champion of 1"). Below the guard, the season still finalizes and the next season opens —
   just with no awards.
4. **Auto-create the next season** during rollover, so seasons stay contiguous (no gap that
   would drop the board to lifetime-XP fallback).
5. Awards are **cosmetic, accumulating** badges shown on the card next to the Lv.10 Legend
   trophy (same display pattern as Phase 2a prestige).

## Data model (migration `006_season_rollover.sql`)

### `game_seasons` — add a column
```sql
ALTER TABLE game_seasons ADD COLUMN IF NOT EXISTS finalized boolean NOT NULL DEFAULT false;
```

### `game_season_award` — new
```sql
CREATE TABLE IF NOT EXISTS game_season_award (
  season_no   int  NOT NULL REFERENCES game_seasons(season_no),
  player_id   uuid NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  rank        int  NOT NULL,
  tier        text NOT NULL,          -- 'champion' | 'finalist'
  awarded_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (season_no, player_id)
);
ALTER TABLE game_season_award ENABLE ROW LEVEL SECURITY;   -- edge-function only, no anon policy
```

### `get_season_standings(p_start date, p_end date)` — new RPC
Returns the **full** ranked field for a season window (not just top N), so the finalize step
can pick the champion + the top-10% finalists:
```sql
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

## Backend — `game-resolve` finalize step

Appended after the existing settle work, wrapped in its own `try/catch` (a finalize failure
must never break the daily settle), idempotent via the `finalized` flag:

```
const nowDate = new Date().toISOString().slice(0,10);
const { data: ended } = await supabase.from("game_seasons")
  .select("season_no, start_date, end_date").lt("end_date", nowDate).eq("finalized", false);
for (const s of ended ?? []) {
  try {
    const { data: standings } = await supabase.rpc("get_season_standings",
      { p_start: s.start_date, p_end: s.end_date });
    const list = standings ?? [];
    if (list.length >= 3) {
      const finalistMax = Math.ceil(list.length * 0.10);   // ranks 1..finalistMax are "in the money"
      for (const row of list) {
        if (row.rank > Math.max(1, finalistMax)) continue;
        const tier = row.rank === 1 ? "champion" : "finalist";
        await supabase.from("game_season_award")
          .upsert({ season_no: s.season_no, player_id: row.player_id, rank: row.rank, tier },
                  { onConflict: "season_no,player_id", ignoreDuplicates: true });
      }
    }
    await supabase.from("game_seasons").update({ finalized: true }).eq("season_no", s.season_no);
    // open the next season (contiguous; start = end + 1 day, end = +2 months)
    const start2 = new Date(s.end_date + "T00:00:00Z"); start2.setUTCDate(start2.getUTCDate() + 1);
    const end2 = new Date(start2); end2.setUTCMonth(end2.getUTCMonth() + 2); end2.setUTCDate(end2.getUTCDate() - 1);
    const iso = (d: Date) => d.toISOString().slice(0,10);
    await supabase.from("game_seasons")
      .upsert({ season_no: s.season_no + 1, name: "Season " + (s.season_no + 1),
                start_date: iso(start2), end_date: iso(end2) }, { onConflict: "season_no", ignoreDuplicates: true });
  } catch (e) { console.error("season finalize error", s.season_no, e); }
}
```

Note: `finalistMax = ceil(n*0.10)`. For n=3 → 1 (champion only). For n=20 → 2 (champion +
1 finalist). For n=100 → 10. Champion is always rank 1; finalists are ranks 2..finalistMax.

## Backend — `game-state`

Add the player's season awards to the response:
```
const { data: awardRows } = await supabase.from("game_season_award")
  .select("season_no, tier").eq("player_id", player.id).order("season_no", { ascending: true });
const season_awards = (awardRows ?? []).map((r) => ({ season_no: r.season_no, tier: r.tier }));
```
Add `season_awards` to `safePlayer`.

## Frontend (`index.html`)

In `gmRenderCharacter`, next to the existing `gm-prestige` (Legend) line, render season
awards from `p.season_awards`:
```js
+((p.season_awards&&p.season_awards.length)?'<div class="gm-prestige">'+p.season_awards.map(function(a){return (a.tier==='champion'?'🥇 S'+a.season_no+' Champion':'🏅 S'+a.season_no+' Finalist');}).join(' ')+'</div>':'')
```
Reuse the `.gm-prestige` style. (Legend + Champion/Finalist can stack as separate small rows.)

## Rollout

Same 3 gates as Phase 2a: ① migration `006` applied to the live DB (Supabase SQL Editor) →
② redeploy `game-resolve` + `game-state` → ③ frontend push (Cloudflare). No new scheduled
job. The first real finalize happens automatically the night after Season 1's `end_date`
(2026-08-16) during the normal `game-resolve` run.

## Out of scope (explicit)

- Season-results screen / history view (awards show on the card; a dedicated results page is
  later).
- Seasonal-return (capital) awards — rewards are by season XP only.
- Notifications when a season ends.
- Backfilling awards for any season that ended before this ships (none have — Season 1 ends
  2026-08-16, well in the future).

## Risks & mitigations

- **Idempotency / double-award** → `finalized` flag gates re-entry; awards `upsert` on
  `(season_no, player_id)` with `ignoreDuplicates`. Safe to run nightly.
- **Finalize failure breaking settle** → the whole step is wrapped in try/catch (per-season
  too), isolated from the human/agent settle paths like the existing roster block.
- **Season gap** → rollover always opens the next season (`upsert` season_no+1), so the board
  never falls back to lifetime XP between seasons.
- **Tiny base** → min-3 guard skips awards but still finalizes + opens the next season.
- **Date/DST** → comparisons use UTC date strings consistent with `game_xp_ledger.trade_date`
  and the Phase 2a season lookups; the ±1 day edge at a boundary is benign (a season finalizes
  one nightly run after it ends).

# Seasons & Prestige (Phase 2a) — Design

**Date:** 2026-06-17
**Status:** Design approved, pending spec review → implementation plan
**Parent:** `2026-06-17-progression-engagement-economy-design.md` (section 2)

## Problem

Reaching max level is a dead end (content cliff), and there is no recurring reason for
engaged/maxed players to return. The parent spec's answer is a hybrid season model:
permanent levels + a resettable seasonal leaderboard + accumulating prestige. This spec
is **Phase 2a** — the cron-free core of that loop.

## Goal

Deliver a recurring competitive loop: a **seasonal XP leaderboard** that resets every 2
months, plus a one-time **"Legend" prestige badge** for reaching max level within a season.
No new cron, no live-table migration, minimal risk.

## Key decisions (locked during brainstorming)

1. **Season XP is derived, not stored.** `game_xp_ledger` already records `xp_delta` per
   `trade_date`. Season XP = `SUM(xp_delta)` over the current season's date window. No
   `season_xp` column on `players`, no reset job.
2. **Seasons live in a `game_seasons` table** (flexible naming/dates), not a code constant.
3. **Scope = Phase 2a (cron-free).** Seasonal leaderboard + inline Lv.10 Legend badge.
   The end-of-season top-% reward (needs a rollover cron) is deferred to Phase 2b.
4. **Hybrid-C persistence:** level, lifetime `xp`, and `capital` all persist across seasons
   (no reset, no demotion). Only the seasonal leaderboard window advances.

## Data model (new — migration `005_seasons.sql`; 004 is the highest existing)

Existing `players` / `game_xp_ledger` tables are NOT altered.

### `game_seasons`
```
season_no   int   PRIMARY KEY
name        text  NOT NULL
start_date  date  NOT NULL
end_date    date  NOT NULL          -- inclusive
```
Seed Season 1: `(1, 'Season 1', '2026-06-17', '2026-08-16')` (today + 2 months;
captures only post-rebalance XP). Dates are in the game's market-date (ET `trade_date`)
terms, so they align with `game_xp_ledger.trade_date`.

### `game_prestige`
```
player_id   uuid  REFERENCES players(id) ON DELETE CASCADE
season_no   int   REFERENCES game_seasons(season_no)
awarded_at  timestamptz DEFAULT now()
UNIQUE (player_id, season_no)
```
One row = a permanent "S{n} Legend" badge.

Both tables get RLS enabled with **no anon policy** (edge-function/service-role only,
matching the existing `players` pattern).

### Season XP (derived)
`season_xp(player) = SUM(game_xp_ledger.xp_delta)` where `trade_date BETWEEN start_date
AND end_date` of the current season.

## Backend changes

### Migration `005_seasons.sql` — also defines two RPCs

`get_season_leaderboard(p_start date, p_end date, p_limit int)` → returns top players:
```sql
SELECT p.display_name, p.level, COALESCE(SUM(l.xp_delta),0)::bigint AS season_xp
FROM game_xp_ledger l JOIN players p ON p.id = l.player_id
WHERE l.trade_date BETWEEN p_start AND p_end
GROUP BY p.id, p.display_name, p.level
HAVING SUM(l.xp_delta) > 0
ORDER BY season_xp DESC
LIMIT p_limit;
```

`get_season_my_rank(p_start date, p_end date, p_device text)` → returns the viewer's own
`season_xp` and `rank` (rank = count of players with a strictly higher season-window sum,
+1), or no row if the viewer has 0 season XP. Both are `SECURITY DEFINER` functions called
with the service-role key.

### `game-leaderboard` (modify)
- `type=xp` branch: look up the current season (`game_seasons` where today ∈ [start,end]);
  call `get_season_leaderboard(...)`; map results into the existing row shape with the `xp`
  field holding **season_xp**. If `device_id` present, call `get_season_my_rank(...)` and set
  `me`. Add `season: { season_no, name, end_date }` to the response.
- `type=return` branch: **unchanged** (lifetime capital + AI merge + pin-my-rank).
- If there is no current season row, fall back to the existing lifetime-`xp` ordering (graceful).

### `game-resolve` (modify — inline prestige award)
In the per-player settle loop, `levelFromXp` is already imported. After the existing
`players` update (which sets `level = levelFromXp(newXp)`):
```
const prevLevel = levelFromXp(player.xp);   // player.xp = pre-update value (already fetched)
const newLevel  = levelFromXp(newXp);
if (prevLevel < 10 && newLevel === 10) {
  const { data: season } = await supabase.from('game_seasons')
    .select('season_no').lte('start_date', tradeDate).gte('end_date', tradeDate).maybeSingle();
  if (season) {
    await supabase.from('game_prestige')
      .upsert({ player_id: playerId, season_no: season.season_no }, { onConflict: 'player_id,season_no', ignoreDuplicates: true });
  }
}
```
Idempotent (UNIQUE + ignoreDuplicates), wrapped so a prestige failure never breaks settle.

### `game-state` (modify — display data)
Add to the response:
- `current_season: { season_no, name, end_date, ends_in_days }` (today vs end_date).
- `player.prestige: [season_no, ...]` (from `game_prestige` for this player).

## Frontend changes (`index.html`)

1. **Leaderboard toggle:** relabel the "⭐ XP" button to "🏆 Season". The render already uses
   `x.xp` for the value, which now carries season_xp — minimal change. Show a header
   "Season 1 · ends in N days" from the response `season` / state `current_season`.
2. **Prestige badges on the character card:** if `state.player.prestige` is non-empty, render
   a small trophy row (e.g., `🏆 S1 Legend`). Hidden when empty.
3. **Season countdown:** "Season N · ends in N days" near the card or leaderboard header,
   from `current_season.ends_in_days`.
4. "💰 Return" board unchanged.

## Rollout

- **No cron.** Deploy order: ① migration `006_seasons.sql` (tables + Season 1 seed + RPCs)
  → ② edge functions `game-leaderboard`, `game-resolve`, `game-state` → ③ frontend (main
  push → Cloudflare). Seasonal board populates as players submit. (Note: migration files in
  the repo stop at 004, but the live DB has later ad-hoc SQL applied directly — so the
  migration must also be RUN against the live DB, via `supabase db push` or the SQL editor,
  not just committed.)
- **No prestige backfill.** Lv.10 badges are awarded going forward only. The game is young
  with slow new rates, so ~0 players are at Lv.10; acceptable. A one-line backfill is possible
  later if needed.
- Live risk is low: new tables + RPCs + mostly reads; existing `players` / `game_xp_ledger`
  untouched.

## Out of scope (explicit)

- **Phase 2b:** end-of-season top-% reward + the rollover cron it requires.
- Capital reset per season (capital persists — hybrid-C).
- Accumulating per-season prestige beyond the one-time Lv.10 badge.
- Season auto-creation: future seasons are seeded manually into `game_seasons` (a few rows
  ahead, or added when needed). No automation in 2a.

## Risks & mitigations

- **Empty current season** (e.g., a gap between seeded seasons) → `game-leaderboard` falls back
  to lifetime-xp ordering; seed seasons contiguously to avoid gaps.
- **Ledger aggregation cost** → small player base. `game_xp_ledger` has no index supporting
  this aggregation today (the existing `(player_id, trade_date)` index is on `game_pick`, not
  the ledger). The migration adds an index on `game_xp_ledger(trade_date)` to keep the season
  sum cheap. Acceptable for now.
- **Prestige award correctness** → gated on the exact `prevLevel<10 && newLevel===10` crossing
  and made idempotent; isolated in try/catch like the existing roster-standings block.
- **Pre-rebalance ledger entries** are excluded because Season 1 starts 2026-06-17 (after the
  Phase 1 rebalance shipped today), so season XP reflects only new rates.

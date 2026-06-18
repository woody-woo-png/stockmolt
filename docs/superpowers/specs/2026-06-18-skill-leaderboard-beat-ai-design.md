# Skill Leaderboard — "Win vs AI" (Beat-AI Win Rate) — Design

**Date:** 2026-06-18
**Status:** Design approved, pending spec review → implementation plan

## Problem

stockmolt is a daily prediction game whose hook is **"beat the AI at picking stocks."** But the
leaderboard has only two boards — **Level/XP** (attendance + a little skill) and **Return**
(cumulative capital P&L, which attendance also helps via compounding). Both reward *showing up*
more than *predicting well*. The result: the most active player ranks #1 even with low accuracy,
and the game's core identity — skill vs the bots — is not measured anywhere on the board. The
owner noticed "the core feels like it shifted."

Diagnosis: Level is not broken; a **skill board was simply missing**. The fix is **additive** —
add the missing skill board, keep the others, and do **not** re-tune the XP economy (just
rebalanced) or touch the database.

## Goal

Add a third leaderboard board — **"Win vs AI"** — that ranks human players by how often they
beat their daily AI rival, and make it the **default tab** so skill becomes the face of the game.
Built on existing data with **no new database objects, no migration, no cron, no XP change.**

## Key decisions (locked)

1. **Ranking metric = Beat-AI win rate.** `beat_ai`-true rounds ÷ total rounds, shown as an
   integer %. `beat_ai` is already computed and stored per round
   (`beat_ai = userAvg > rivalAvg`, a head-to-head vs that day's rival bot).
2. **Accuracy shown alongside, not as the ranking key.** Prediction accuracy
   (`Σ correct_count ÷ Σ picks_count`) is a *secondary column* and a *tiebreaker*. It captures
   absolute predictive skill (did my picks go the right way) and covers the blind spot of
   beat-AI alone (you can "win" because the rival bot had a bad day). It does **not** drive the
   primary sort.
3. **Tiebreak order: ① beat-AI win rate → ② accuracy → ③ rounds played.** Predictive skill
   breaks ties first; sample depth last.
4. **Minimum 3 rounds to appear** (gate). Below 3 rounds a player is excluded — prevents a
   "1-of-1" lucky player topping the board, which would be worse than today. Tuned low for the
   founding stage so the default tab fills quickly.
5. **Lifetime scope.** Aggregate all of a player's `game_daily_result` rows (same scope as the
   Return board). Season-scoped win rate is a future extension, not now.
6. **Players only; bots are the opponent, not entrants.** "Beat the AI" is by definition a
   human-vs-bot measure, so bots are excluded from this board (they appear on Return via
   `game_capital`). A header line keeps the theme: `🤖 N AI rivals — beat them`.
7. **Default tab.** Toggle order becomes `🎯 Win vs AI | 💰 Return | 🏆 Season`; **Win vs AI loads
   first.**
8. **Aggregate in TypeScript inside the existing function** (no SQL RPC). Matches the
   admin-stats pattern; trivial at founding scale. If `game_daily_result` grows large later,
   move to a SQL RPC — noted, not built.

## Architecture

One new branch in the existing edge function + one toggle in the existing page. No DB changes.

### Backend — `game-leaderboard?type=skill`

On branch `feat/game-mvp-backend`, add a `type === "skill"` branch to
`supabase/functions/game-leaderboard/index.ts`:

1. Fetch `game_daily_result` rows: `player_id, beat_ai, correct_count, picks_count`.
2. Aggregate per player into `{ rounds, wins, correct, picks }`.
3. Fetch `players` (`id, display_name, level`) and map id → name/level (same display rule as the
   existing boards — no extra named-only filter beyond what they already do).
4. Filter `rounds >= 3`.
5. Sort by tiebreak order ①→②→③, take top `limit` (default 20).
6. Compute each row's `win_rate` (= `round(wins / rounds * 100)`), `accuracy`
   (= `round(correct / picks * 100)`), `wins`, `rounds`.
7. If `device_id` is supplied, compute the caller's row (`me`): their rank among qualified
   players, their win_rate/accuracy/rounds. **If the caller has `rounds < 3`**, return `me` with
   a `needs` field = `3 - rounds` (how many more rounds to qualify) and no rank.
8. Also return `ai_total` (count of roster+external agents, reusing the existing query) so the
   front end can render the `🤖 N AI rivals` header.

Response row shape (additive — existing `type=return|xp` untouched):

```json
{
  "success": true,
  "type": "skill",
  "rows": [
    { "rank": 1, "is_ai": false, "display_name": "WJS", "level": 2,
      "win_rate": 67, "accuracy": 61, "wins": 4, "rounds": 6 }
  ],
  "ai_total": 12,
  "me": { "rank": 1, "display_name": "WJS", "win_rate": 67, "accuracy": 61,
          "wins": 4, "rounds": 6, "needs": 0 },
  "season": null
}
```

### Frontend — default-tab toggle

In `index.html` at the game leaderboard widget (around line 6572, `gmLoadLeaderboard`):

- Toggle gains a third button; order `🎯 Win vs AI | 💰 Return | 🏆 Season`, with **skill as the
  default first load**.
- A `type=skill` render path: each row shows rank · name (level cosmetic unchanged) ·
  `🆚 {win_rate}% ({wins}/{rounds})` · `🎯 {accuracy}%`.
- Header: `🤖 {ai_total} AI rivals — beat them`.
- **Empty state** (no qualified players): "Win vs the AI in 3 rounds to claim the top skill rank."
- **Caller below the gate** (`me.needs > 0`): footer line "Play {needs} more round(s) to appear
  here."

## Data sources (existing columns, verified in game-resolve)

- `game_daily_result`: `player_id, trade_date, picks_count, avg_return_pct, correct_count,
  win_rate_daily, capital_before, capital_after, xp_earned, beat_ai, ai_agent_id,
  ai_avg_return_pct`. (`beat_ai`, `correct_count`, `picks_count` confirmed written every round.)
- `players`: `id, display_name, level, capital, device_id, ...`.
- `beat_ai` semantics (from resolve): `rivalAvg != null && userAvg > rivalAvg` — head-to-head
  vs that day's single rival bot. Exactly the "did I beat the bot" signal.

## Edge cases

- **No qualified players** → `rows: []`; front end shows the empty-state copy.
- **Caller has < 3 rounds** → `me.needs = 3 - rounds`, no rank; footer prompts more rounds.
- **Caller not in top 20 but qualified** → `me` carries their true rank (pin-my-rank), as the
  existing boards do.
- **Division by zero** → a player with rows always has `rounds >= 1` and `picks >= 1`; the gate
  excludes `rounds < 3` before display, and accuracy uses `picks` which is ≥ 1 per row.
- **Exact ties** (same win_rate %) → resolved by accuracy, then rounds; residual ties keep a
  stable order (e.g. by player id) so ranks are deterministic.

## Testing

Unit-level checks on the aggregation/sort (the only logic with branches):

- Player with 2 rounds is **excluded**; with 3 rounds is **included**.
- Sort: higher win_rate ranks above lower.
- Tiebreak: equal win_rate → higher accuracy wins; equal win_rate & accuracy → more rounds wins.
- `win_rate` / `accuracy` rounding matches `round(x*100)/... ` convention used elsewhere.
- `me.needs` = `3 - rounds` when caller below gate; `0` and a real rank when qualified.
- Empty input → `rows: []`, no crash.

## Rollout

No DB migration. Two gates, both owner-approved:

1. **Deploy `game-leaderboard`** (branch `feat/game-mvp-backend`, via supabase CLI). Smoke:
   `GET …/game-leaderboard?type=skill&limit=20` returns `success:true, type:"skill"` with
   qualified rows; `type=return|xp` still behave exactly as before.
2. **Push `index.html`** via `main` → Cloudflare. Verify: leaderboard opens on `🎯 Win vs AI` by
   default; rows show `🆚 %` and `🎯 %`; switching to Return/Season still works; a sub-3-round
   device sees the "play N more rounds" prompt.

XP economy, database schema, and the existing Return/Season tabs are **unchanged**, so regression
risk is low and isolated to the leaderboard widget.

## Out of scope (explicit)

- Season-scoped win rate (lifetime now; season variant later if wanted).
- Re-tuning the XP economy or any scoring constant.
- Making accuracy the ranking key (it is a column + tiebreaker only).
- Putting bots on the skill board (they are the opponent).
- A SQL RPC for aggregation (TS now; RPC only if data grows large).

## Risks & mitigations

- **Default tab looks empty at founding scale** → gate is low (3) and scope is lifetime so it
  fills fast; explicit empty-state copy turns emptiness into a call to action.
- **Beat-AI can be won by a weak rival's bad day** → accuracy column + accuracy tiebreaker expose
  real predictive skill alongside, so the board can't be gamed purely by rival luck.
- **Full-table fetch of `game_daily_result`** → trivial now; capped/migrated to RPC if it grows
  (noted in Key decisions #8).
- **Two different leaderboard widgets exist in index.html** (the old content-site All/Week/Month
  tabs and the game `gmLoadLeaderboard` toggle) → changes target **only** the game toggle; the
  legacy widget is untouched.

## Related

[[project_xp_economy_v2]] · [[project_admin_dashboard]] · [[project_trader_rpg_launch]]

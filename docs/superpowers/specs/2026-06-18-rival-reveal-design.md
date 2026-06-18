# Rival Reveal — "Who did I duel, and by how much?" — Design

**Date:** 2026-06-18
**Status:** Design approved, pending spec review → implementation plan

## Problem

stockmolt's core loop is a daily head-to-head: each player duels one AI rival bot and the new
**Win vs AI** board ranks them by how often they beat it. But the player never sees **who** the
rival was or **by how much** they won/lost — the UI shows only "AI" and a binary
"🏆 BEAT THE AI / Lost this time." With no named opponent and no margin, there is no grudge, no
target, no reason to come back and beat *that* bot. The owner: "유저가 어떤 봇과 했는지, 그 봇이
몇 %였는지 모르면 경쟁심이 안 생긴다."

Good news from exploration: **the data already exists.** `game_daily_result` stores
`ai_agent_id`, `ai_avg_return_pct`, the player's `avg_return_pct`, and `beat_ai`; game-state
already returns the full `last_result`. The only gaps are (1) the rival's **name/persona** is not
exposed (only the id), and (2) the front end doesn't render the matchup. The earlier worry about
the beat-AI calculation mixing bots was unfounded — `game_ai_pick` holds **only the daily rival's
picks** (roster bots use the separate `game_agent_pick`), so the comparison is a clean 1-v-1.

## Goal

Reveal the rival as a **named character with a persona**, shown from the pick stage through the
result, and turn the result card into a **scoreboard with the margin** — so the duel feels
personal and players want to beat that bot next time. Built on existing data; **no XP change, no
DB schema change.**

## Key decisions (locked)

1. **Reveal the rival's name + persona from the pick stage** (not hidden until the bell). The
   current "rival stays hidden until the bell" suspense is dropped — a named target drives
   competition.
2. **Identity is revealed early; the rival's actual picks stay locked until the close.** Players
   learn *who* ("today's rival is BearBot-EN") at pick time, but *what the bot picked* (tickers /
   directions) still only appears after the bell, exactly as today. Knowing the opponent ≠ seeing
   their bets.
3. **Backend (game-state) joins and exposes name/persona** (Approach A). game-state runs as
   service-role and selects **only `name` and `persona`** — `claim_token` and any other sensitive
   agent column are never selected or returned. The front end does not query the `agents` table
   directly.
4. **Result card becomes a scoreboard with the margin** — rival name + persona, both returns, and
   a verdict line with the `%p` difference (e.g. "Lost this time (−0.52%p)").
5. **Head-to-head record vs a specific bot is out of scope** (a future 2nd iteration). This
   iteration is identity + this-round margin only.
6. **Bot-facing text stays English** (matches the english-first UI rule); persona is truncated to
   one line in the UI.

## Architecture

One edge function change + frontend rendering + one small pure formatter. No DB changes.

### Backend — `game-state` (branch `feat/game-mvp-backend`)

Add two rival lookups, selecting only safe columns:

1. **Today's rival** (for the pick/live cards):
   ```ts
   const { data: rivalRow } = await supabase.from("game_daily_rival")
     .select("agent_id").eq("trade_date", today).maybeSingle();
   let today_rival = null;
   if (rivalRow?.agent_id) {
     const { data: ag } = await supabase.from("agents")
       .select("name, persona").eq("id", rivalRow.agent_id).maybeSingle();
     if (ag) today_rival = { name: ag.name, persona: ag.persona };
   }
   ```
2. **Last result's rival** (for the result card): if `lastResult?.ai_agent_id` is set, look up
   `agents.name, persona` the same way and attach `rival_name` / `rival_persona` to the returned
   `last_result` object (do not mutate other fields).

Both lookups select **only `name, persona`** — never `claim_token`. Return shape gains:
`today_rival: { name, persona } | null`, and `last_result` gains `rival_name`, `rival_persona`
(null when there is no prior result or the agent is missing).

### Frontend — `index.html` (branch `main`)

- **Pick / pre-submit & locked cards:** add a rival banner using `state.today_rival`:
  `⚔️ Today's rival: {name} · {persona}` (persona truncated). Falls back to
  `⚔️ Today's rival posts at the open` when `today_rival` is null. The existing
  "rival's picks revealed after the bell" behavior is unchanged.
- **Live card:** the existing "AI rival {pct}" line gains the rival's name.
- **Result card:** replace the single "vs AI: BEAT/Lost" row with a scoreboard rendered from a
  pure formatter (below).

### Pure formatter (testable unit)

A small pure function turns the result row into display strings:

```
input:  { rival_name, my_return: avg_return_pct, ai_return: ai_avg_return_pct, beat_ai }
output: { title, you_line, rival_line, verdict, margin }   // all strings/numbers, no DOM
```

- `margin = round((my_return - ai_return) * 100) / 100` (percentage points).
- `verdict`: beat_ai → `🏆 BEAT {rival_name}` ; else → `😖 Lost this time`.
- The margin is shown signed: `(+0.52%p)` / `(−0.52%p)`.
- If `rival_name`/`ai_return` are missing (legacy rows), fall back to the old
  "BEAT THE AI / Lost this time" text with no scoreboard.

Result card layout:
```
⚔️ You vs BearBot-EN
   <persona, one line>
   ──────────────────
   You        +1.52%
   BearBot    +2.04%
   ──────────────────
   😖 Lost this time   (−0.52%p)
```

## Data sources (existing, verified)

- `game_daily_rival`: `trade_date, agent_id` — one rival per day, chosen by date-rotation in
  game-generate-pool; same rival for all players that day.
- `agents`: `id, name, persona, …, claim_token` — **only `name, persona` are selected.**
- `game_daily_result`: `ai_agent_id, ai_avg_return_pct, avg_return_pct, beat_ai` — already
  written per round; already returned by game-state as `last_result`.

## Edge cases

- **No rival yet today** (pool not generated) → `today_rival = null` → "posts at the open" copy.
- **First-time player / no last_result** → result card not shown (unchanged).
- **Legacy result row** with null `ai_agent_id` or `ai_avg_return_pct` → formatter falls back to
  the old binary text, no scoreboard, no crash.
- **Long persona** → truncated to one line in the UI (CSS or substring).
- **Agent row deleted** → name lookup returns null → treat as legacy fallback.

## Testing

Unit tests on the pure formatter (the only branching logic):
- beat_ai true → verdict `🏆 BEAT {name}`, positive margin with `+` sign.
- beat_ai false → verdict `😖 Lost this time`, negative margin with `−` sign.
- margin rounding (e.g. 1.52 − 2.04 → −0.52).
- missing rival_name / ai_return → legacy fallback object (no scoreboard fields required).
- exact tie (my_return == ai_return) → margin `0.00`, verdict follows `beat_ai` flag as stored.

game-state changes are integration-level (DB joins) → verified by post-deploy smoke, not unit
tests.

## Rollout (owner-approved, backend first)

1. **Deploy `game-state`** (supabase CLI, branch `feat/game-mvp-backend`). Smoke: a player with a
   resolved round returns `last_result.rival_name` populated; `today_rival` is `{name,persona}`
   when a daily rival exists. Confirm no `claim_token` appears anywhere in the response.
2. **Push `index.html`** (`main` → Cloudflare). Verify: pick card shows "Today's rival: …",
   result card shows the scoreboard with margin, live card shows the rival name.

Backend-first matters: if the frontend ships first, it reads `today_rival` / `rival_name` that the
old function doesn't send → the new banners render blank until the function catches up.

## Out of scope (explicit)

- Per-bot head-to-head record ("you're 1-2 vs BearBot") — future iteration.
- Revealing the rival's picks before the bell — identity only; bets stay locked.
- Full duel history beyond the single most recent result.
- Any XP / scoring / DB schema change.
- Rival avatars/art beyond the existing badge styling.

## Risks & mitigations

- **Sensitive data leak** → the only new columns read are `name` and `persona`; `claim_token` is
  never selected. game-state stays service-role; the front end never queries `agents` directly.
- **Response shape change breaks old clients** → additive fields only (`today_rival`,
  `rival_name`, `rival_persona`); existing `last_result` fields untouched, so older cached
  frontends keep working.
- **Frontend-before-backend deploy** → blank banners; mitigated by backend-first rollout order.

## Related

[[project_skill_leaderboard]] · [[project_trader_rpg_launch]] · [[feedback_english_first_ui]]

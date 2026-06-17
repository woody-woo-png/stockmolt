# Progression & Engagement Economy v2 — Design

**Date:** 2026-06-17
**Status:** Design approved, pending spec review → implementation plan

## Problem

The trader RPG launched with an XP economy that feels too generous, and the
owner's instinct ("players level up too fast") is correct — but the precise
diagnosis matters, because the obvious fix (raise level thresholds) is wrong.

Verified facts from `supabase/functions/_shared/game_logic.ts`
(branch `feat/game-mvp-backend`):

```
LEVEL_THRESHOLDS = [0, 100, 250, 500, 850, 1300, 1900, 2700, 3800, 5200]  // 10 levels
XP = { SUBMIT: 50, RESULT: 30, CORRECT_EACH: 10, BEAT_AI: 30, STREAK_3: 50, STREAK_7: 150 }
```

One round per trading day (pick 3 of 6, same-day settle). Per round:
- `SUBMIT 50` at submit + `RESULT 30` at resolve = **80 XP/day guaranteed,
  skill-independent** (the freeloader floor).
- `CORRECT_EACH 10 × correct (0–3)` + `BEAT_AI 30` = skill bonus, max +60/day.

**Pacing reality (trading days to Lv.10 = 5200 XP):**
- Strong player (3/3 + beat AI = 140/day): **~37 days ≈ one 2-month season.**
- Zero-skill freeloader (floor 80/day): **~65 days.**

So total-to-max length was never the problem. The problem is the **skill-independent
floor is too high** — clicking submit and viewing the result levels you up. And two
structural gaps amplify the "ran out of game" feeling:

1. **Streak rewards die at day 7** — nothing rewards consistency past a week.
2. **Mid-level unlocks are empty** — Lv.2, 4, 6, 7, 8, 9 grant only a badge
   (`GM_UNLOCKS` in `index.html`), so felt progression dies even while the number grind continues.
3. **No endgame** — reaching Lv.10 is a dead end (content cliff).

## Goal

Increase engagement, not merely slow XP. Slowing XP **in isolation would reduce
engagement** (less reward per session, no new reason to return). The fix pairs a
source rebalance with stronger daily-return hooks and a recurring endgame.

Three engagement legs, designed as one coherent economy, shipped in two phases:
1. **Daily return** — extend streaks.
2. **Progression depth** — rebalance XP sources + fill unlock gaps.
3. **Endgame** — seasons + prestige, so max level is a recurring gateway.

## Key decisions (locked)

- **Keep `LEVEL_THRESHOLDS` at 5200.** Raising thresholds re-computes existing
  players' levels and demotes them — the exact harm hybrid seasons were chosen to avoid.
- **Hybrid season model (C):** permanent levels (no reset, no demotion) + a
  resettable seasonal leaderboard + accumulating prestige badges.
- **Season length: 2 months.**
- **Two-track XP:** `lifetime_xp` (permanent level) and `season_xp` (resettable
  leaderboard / prestige qualification), both incremented on every award.

---

## Phase 1 — Source rebalance + streaks + unlocks

No new tables. Ships on the existing `feat/game-mvp-backend` branch. Directly
answers the original "XP too generous" complaint.

### 1-a. XP source rebalance

| Constant | Current | New | Meaning |
|---|---|---|---|
| `SUBMIT` | 50 | **15** | participate |
| `RESULT` | 30 | **10** | view result |
| `CORRECT_EACH` | 10 | **20** | per correct pick (3/3 = 60) |
| `BEAT_AI` | 30 | **40** | beat the AI rival |

Resulting pacing (trading days to Lv.10):

| Player | XP/day | Days to max |
|---|---|---|
| Zero-skill freeloader | floor 25 | **~200+** (effectively never without skill) |
| Realistic good (~2/3 correct + beat AI ~½ ≈ 85) | 85 | **~1.5 seasons** |
| Perfect ceiling (3/3 + beat AI daily) | 125 | **~1 season** |

Skill now drives ~70% of a good player's XP. Strong-player pace barely moves; the
freeloader path is what dies. **Level thresholds unchanged.**

### 1-b. Streak extension

Extend `resultXp` milestones beyond day 7:

```
3 day  → +50
7 day  → +150
14 day → +300
30 day → +600
100 day→ +2000
```

Backend: add milestones to `XP` and the `newStreak === N` checks in `resultXp`.
Frontend: `GM_STREAK_MILESTONES` / `GM_STREAK_BONUS` mirror constants in
`index.html` must be kept in sync (same hardcoded-drift caveat already noted there).

### 1-c. Fill mid-level unlock gaps

All client-side cosmetics (no backend). Update `GM_UNLOCKS` in `index.html`:

| Lv | Existing | Added cosmetic |
|---|---|---|
| 2 🔍 | — | profile card accent color |
| 3 📡 | Name highlight | (unchanged) |
| 4 🎯 | — | animated badge glow |
| 5 ⚔️ | Colored nickname | (unchanged) |
| 6 🌊 | — | leaderboard row shimmer |
| 7 🎲 | — | custom card theme |
| 8 🦅 | — | profile frame |
| 9 🛡️ | — | nickname aura / animation |
| 10 👑 | Hall of Fame | (unchanged) |

### 1-d. Existing-player nerf framing

The floor cut (80→25/day, ~70%) is a real felt nerf even though hybrid-C protects
levels from demotion. Mitigation: **apply the rate change at a season boundary**,
framed as a "Season N scoring update." If Phase 1 ships before the season system
exists, communicate it as a scoring update via in-app notice. Seasons are the cover
for the rebalance — do not drop it silently mid-season.

---

## Phase 2 — Seasons + prestige endgame

Heavier infrastructure (new tables + cron). Deployed separately, aligned to a
season boundary (also the clean moment to apply the Phase 1 nerf if not yet live).

### 2-a. Two-track XP data model

| Track | Resets | Drives |
|---|---|---|
| `lifetime_xp` (existing `xp`) | never | permanent level (hybrid-C, no demotion) |
| `season_xp` (new) | each season → 0 | seasonal leaderboard + prestige qualification |

Both increment together on every award. Level math reads `lifetime_xp`; seasonal
leaderboard reads `season_xp`.

### 2-b. Season definition & rollover

- 2-month fixed calendar windows; a `seasons` config holds number + start + end.
- Season-end rollover job (cron): snapshot final leaderboard → award prestige /
  top-% rewards → reset `season_xp` to 0 → increment season number.

### 2-c. Seasonal leaderboard

- The current leaderboard becomes **"this season"** (ranked by `season_xp` /
  seasonal return), resetting each season.
- Optional secondary "All-time" tab ranked by `lifetime_xp`.

### 2-d. Prestige rewards

- **Reach Lv.10 within a season → permanent "S{n} Legend" badge.** Accumulates on
  the profile (collection / trophy-case feel) — this is what re-hooks already-maxed
  climbers, covering hybrid-C's weakness (otherwise "rank resets but level doesn't"
  feels thin for them).
- **Top 10% of the season leaderboard → season-limited cosmetic / title.**
  "This season only" creates return urgency. (10% is the starting tuning value.)
- Already-maxed players chase a fresh leaderboard + a fresh prestige badge every season.

### 2-e. Infrastructure

- `players.season_xp` column (or a `player_seasons` table).
- `seasons` config table.
- Season-rollover cron function (snapshot, award, reset).
- Prestige badge storage (`player_prestige` array/table).
- Leaderboard query gains a season filter.

---

## Phasing summary

| | Content | Infra | Deploy |
|---|---|---|---|
| **Phase 1** | XP rebalance + streak extension + unlock fills | 0 new tables | existing branch, now |
| **Phase 2** | seasons + `season_xp` + prestige + rollover | new tables + cron | separate, at a season boundary |

Phase 1 resolves the original complaint immediately and is independently valuable.
Phase 2 fills the endgame. The Phase 1 nerf lands cleanly at the Phase 2 season boundary.

## Out of scope (explicit)

- Push notifications / re-engagement (a separate retention axis; noted as a future
  lever but not designed here).
- Daily missions / quests.
- Changing the core daily loop (pick window, same-day settle) — unchanged.
- Monetization tie-ins (deferred per existing project direction).

## Risks & mitigations

- **Felt nerf for existing engaged players** → tie the rate change to a season
  boundary + scoring-update notice (1-d).
- **Hardcoded streak/unlock constants drift** between backend `game_logic.ts` and
  `index.html` mirrors → keep the existing "keep in sync" code comments; extend them
  to the new milestones.
- **Two-track XP migration** → `season_xp` is additive (new column defaulting to 0
  or backfilled from current-season activity); `lifetime_xp` is the existing `xp`,
  untouched. No level recompute, no demotion.

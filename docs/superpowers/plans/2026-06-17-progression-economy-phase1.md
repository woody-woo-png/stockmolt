# Progression Economy Phase 1 (XP Rebalance + Streak Extension) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kill the skill-independent XP floor (so leveling reflects skill) and extend streak rewards past day 7, without changing level thresholds (no player demotion).

**Architecture:** Pure-function constants live in `supabase/functions/_shared/game_logic.ts` (Deno), consumed by the `game-resolve` / `game-submit-picks` edge functions. The frontend `index.html` holds hardcoded *mirror* constants for streak previews that must stay in sync. Backend code lives on branch `feat/game-mvp-backend`; the live frontend `index.html` lives on `main`.

**Tech Stack:** Deno (Supabase Edge Functions), TypeScript, vanilla JS frontend, Supabase CLI for deploy.

**Spec:** `docs/superpowers/specs/2026-06-17-progression-engagement-economy-design.md` (Phase 1, sections 1-a, 1-b).

**Scope note:** Spec section 1-c (mid-level cosmetic unlock fills) is intentionally NOT in this plan — it is per-element UI work and gets its own frontend plan after this ships.

---

## Branch & deploy reality (read before starting)

- **Tasks 1–2** edit backend files → work on branch `feat/game-mvp-backend`.
- **Task 3** edits `index.html` (the live site) → work on branch `main`.
- **Task 4** deploys the changed edge functions to Supabase (live behavior change → requires 지크님's explicit approval before running).
- This is a real rate change for existing live players (floor 80→25/day). Per spec 1-d, coordinate a short user-facing notice ("scoring update") at deploy time. There is no in-app notice system yet, so this is a manual announcement step in Task 4.

---

## Prerequisite Task 0: Install Deno (test runner)

`deno` is not installed locally; the backend unit tests are Deno tests.

- [ ] **Step 1: Install Deno (Windows, PowerShell)**

Run:
```powershell
winget install DenoLand.Deno
```
If `winget` is unavailable, run:
```powershell
irm https://deno.land/install.ps1 | iex
```

- [ ] **Step 2: Verify install (open a fresh shell first)**

Run: `deno --version`
Expected: prints a `deno 1.x` / `2.x` version line. If "not recognized", reopen the terminal so PATH refreshes.

- [ ] **Step 3: Check out the backend branch**

Run: `git checkout feat/game-mvp-backend`
Expected: `Switched to branch 'feat/game-mvp-backend'`.

- [ ] **Step 4: Baseline — run the existing tests green**

Run: `deno test supabase/functions/_shared/game_logic_test.ts`
Expected: all tests PASS (this confirms the toolchain works before we change anything).

---

## Task 1: Rebalance XP source constants

Lower the skill-independent floor (`SUBMIT`, `RESULT`) and raise the skill bonuses (`CORRECT_EACH`, `BEAT_AI`). `LEVEL_THRESHOLDS` is unchanged.

**Files:**
- Modify: `supabase/functions/_shared/game_logic.ts` (the `XP` object)
- Test: `supabase/functions/_shared/game_logic_test.ts` (update existing `resultXp: 합산과 내역` expectation)

- [ ] **Step 1: Update the failing test first**

In `supabase/functions/_shared/game_logic_test.ts`, change the `resultXp: 합산과 내역` test's expected total from `130` to `140` (new math: RESULT 10 + 2×CORRECT_EACH 20 + BEAT_AI 40 + STREAK_3 50 = 140):

```ts
Deno.test("resultXp: 합산과 내역", () => {
  const r = resultXp({ correctCount: 2, beatAi: true, newStreak: 3 });
  assertEquals(r.total, 140);
  assertEquals(r.breakdown.length, 4);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `deno test supabase/functions/_shared/game_logic_test.ts --filter "합산과 내역"`
Expected: FAIL — actual `130`, expected `140` (constants still old).

- [ ] **Step 3: Update the constants**

In `supabase/functions/_shared/game_logic.ts`, change the `XP` object's four source values (leave `STREAK_3` / `STREAK_7` as-is for now — those change in Task 2):

```ts
export const XP = {
  SUBMIT: 15,
  RESULT: 10,
  CORRECT_EACH: 20,
  BEAT_AI: 40,
  STREAK_3: 50,
  STREAK_7: 150,
};
```

- [ ] **Step 4: Run the full test file to verify green**

Run: `deno test supabase/functions/_shared/game_logic_test.ts`
Expected: all PASS. (The `resultXp: 무적중·패배·스트릭1` test asserts `total === XP.RESULT` symbolically, so it still passes at the new `RESULT=10`.)

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/_shared/game_logic.ts supabase/functions/_shared/game_logic_test.ts
git commit -m "feat(game): rebalance XP sources — cut skill-independent floor (50/30→15/10), raise skill bonus (10/30→20/40)"
```

---

## Task 2: Extend streak milestones past day 7

Add 14 / 30 / 100-day streak bonuses. `resultXp` already loops its `breakdown` into `game_xp_ledger` in `game-resolve`, so no resolve-function change is needed — only the pure module.

**Files:**
- Modify: `supabase/functions/_shared/game_logic.ts` (`XP` object + `resultXp` body)
- Test: `supabase/functions/_shared/game_logic_test.ts` (add milestone tests)

- [ ] **Step 1: Write failing tests**

Append to `supabase/functions/_shared/game_logic_test.ts`:

```ts
Deno.test("resultXp: 14일 스트릭 보너스", () => {
  const r = resultXp({ correctCount: 0, beatAi: false, newStreak: 14 });
  assertEquals(r.total, 310); // RESULT 10 + STREAK_14 300
  assertEquals(r.breakdown.length, 2);
});

Deno.test("resultXp: 30일 스트릭 보너스", () => {
  const r = resultXp({ correctCount: 0, beatAi: false, newStreak: 30 });
  assertEquals(r.total, 610); // RESULT 10 + STREAK_30 600
});

Deno.test("resultXp: 100일 스트릭 보너스", () => {
  const r = resultXp({ correctCount: 0, beatAi: false, newStreak: 100 });
  assertEquals(r.total, 2010); // RESULT 10 + STREAK_100 2000
});

Deno.test("resultXp: 비마일스톤 스트릭은 보너스 없음", () => {
  const r = resultXp({ correctCount: 0, beatAi: false, newStreak: 8 });
  assertEquals(r.total, 10); // RESULT only — streak 8 is not a milestone
  assertEquals(r.breakdown.length, 1);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `deno test supabase/functions/_shared/game_logic_test.ts --filter "스트릭"`
Expected: the 14/30/100 tests FAIL (totals come back as `10` — no bonus added yet).

- [ ] **Step 3: Add constants + milestone checks**

In `supabase/functions/_shared/game_logic.ts`, add three constants to `XP`:

```ts
export const XP = {
  SUBMIT: 15,
  RESULT: 10,
  CORRECT_EACH: 20,
  BEAT_AI: 40,
  STREAK_3: 50,
  STREAK_7: 150,
  STREAK_14: 300,
  STREAK_30: 600,
  STREAK_100: 2000,
};
```

In the same file, add the new milestone branches inside `resultXp`, right after the existing `streak_7` line:

```ts
  if (newStreak === 3) breakdown.push({ reason: "streak_3", xp: XP.STREAK_3 });
  if (newStreak === 7) breakdown.push({ reason: "streak_7", xp: XP.STREAK_7 });
  if (newStreak === 14) breakdown.push({ reason: "streak_14", xp: XP.STREAK_14 });
  if (newStreak === 30) breakdown.push({ reason: "streak_30", xp: XP.STREAK_30 });
  if (newStreak === 100) breakdown.push({ reason: "streak_100", xp: XP.STREAK_100 });
```

- [ ] **Step 4: Run the full test file to verify green**

Run: `deno test supabase/functions/_shared/game_logic_test.ts`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/_shared/game_logic.ts supabase/functions/_shared/game_logic_test.ts
git commit -m "feat(game): extend streak milestones — add 14/30/100-day bonuses (+300/+600/+2000)"
```

---

## Task 3: Sync frontend streak mirror constants

The frontend hardcodes streak previews that must match the backend. `gmStreakInfo` and `gmStreakCheck` already iterate the arrays generically, so only the two constants change.

**Files:**
- Modify: `index.html:5926-5927` (on branch `main`)

- [ ] **Step 1: Switch to the live frontend branch**

Run: `git checkout main`
Expected: `Switched to branch 'main'`.

- [ ] **Step 2: Update the mirror constants**

In `index.html`, replace lines 5926–5927:

```js
    const GM_STREAK_MILESTONES = [3, 7];
    const GM_STREAK_BONUS = {3: 50, 7: 150};
```

with:

```js
    const GM_STREAK_MILESTONES = [3, 7, 14, 30, 100];
    const GM_STREAK_BONUS = {3: 50, 7: 150, 14: 300, 30: 600, 100: 2000};
```

Leave the existing "mirrors backend XP.STREAK_3 / XP.STREAK_7 (game_logic.ts) — keep in sync" comment on line 5925; it now covers all five milestones.

- [ ] **Step 3: Verify the consumers handle the longer array (read-only check)**

Confirm (by reading, no change needed) that:
- `gmStreakInfo` (`index.html:6214`) loops `GM_STREAK_MILESTONES` to find the next milestone — works for any length.
- `gmStreakCheck` (`index.html:6320`) loops the same array to pick the highest hit milestone — works for any length.

Expected: both already generic; no further edits.

- [ ] **Step 4: Smoke-check in a browser**

Open `index.html` locally (or the deployed preview) and confirm no JS console errors on the game screen, and the streak progress text renders (e.g., "M days to 🎁 +50 XP").
Expected: page loads, no errors, streak bar/text present.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat(game): sync frontend streak mirror to 14/30/100-day milestones"
```

---

## Task 4: Deploy backend functions (APPROVAL GATE)

The XP changes only take effect once the edge functions that import `game_logic.ts` are redeployed. This is a **live behavior change for real players** — get 지크님's explicit approval before running.

**Functions importing `game_logic.ts`:** `game-resolve`, `game-submit-picks`, `game-submit-agent-picks`.

- [ ] **Step 1: Confirm approval + timing**

Confirm with 지크님: deploy now? Prefer a low-traffic window. Prepare the short user notice ("Season scoring update — XP now rewards skill more, streaks now go to 100 days") to post wherever players are reached.

- [ ] **Step 2: Check out the backend branch**

Run: `git checkout feat/game-mvp-backend`
Expected: on `feat/game-mvp-backend` with Tasks 1–2 committed.

- [ ] **Step 3: Deploy the three functions**

Run:
```bash
supabase functions deploy game-resolve game-submit-picks game-submit-agent-picks
```
Expected: each reports a successful deploy. (Supabase function deploys incur no usage cost.)

- [ ] **Step 4: Smoke-verify the live behavior**

In the live game UI, submit a round and confirm the `+XP` flash shows **+15** (was +50). After the next resolve cycle, confirm a result's XP breakdown reflects the new numbers (e.g., a 2/3-correct + beat-AI day = 10 + 40 + 40 = 90, plus any streak milestone).
Expected: submit flash = +15; resolved XP matches the new constants.

- [ ] **Step 5: Post the user notice**

Post the prepared "scoring update" message to the player channel(s).

---

## Self-Review notes

- **Spec coverage:** 1-a (source rebalance) → Task 1. 1-b (streak extension) → Tasks 2–3. 1-d (nerf framing/notice) → Task 4 steps 1 & 5. 1-c (cosmetics) → explicitly deferred to a separate plan (stated up top).
- **Thresholds unchanged:** no task touches `LEVEL_THRESHOLDS` — no player demotion, consistent with hybrid-C. Verified.
- **Type/name consistency:** `STREAK_14/30/100` constants and `streak_14/30/100` ledger reasons are used identically in Task 2 steps 1 and 3. Frontend keys `14/30/100` in Task 3 match.
- **No new resolve-function code:** confirmed `game-resolve` already loops `resultXp().breakdown` into `game_xp_ledger`, so new milestone reasons flow automatically.

---

## Execution Handoff

This plan touches two branches and ends in a live deploy with an approval gate — best run with review between tasks.

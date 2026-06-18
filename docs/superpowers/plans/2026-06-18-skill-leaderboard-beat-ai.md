# Skill Leaderboard "Win vs AI" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third leaderboard board — "Win vs AI" — ranking human players by beat-AI win rate, as the default tab, with accuracy as a secondary column + tiebreaker and a 3-round gate.

**Architecture:** A pure aggregation function (`_shared/skill_board.ts`, unit-tested with Deno) computes the board from raw `game_daily_result` + `players` rows. The existing `game-leaderboard` edge function gains a `type=skill` branch that fetches the rows and calls it. `index.html`'s game leaderboard toggle gains a `🎯 Win vs AI` button and renders the new shape, defaulting to it. No DB schema change, no migration, no XP change.

**Tech Stack:** Deno / TypeScript (Supabase Edge Functions), vanilla JS in `index.html`, Deno's std `assertEquals` for tests.

**Spec:** `docs/superpowers/specs/2026-06-18-skill-leaderboard-beat-ai-design.md`

---

## Branch strategy (IMPORTANT — read first)

The backend functions live **only** on branch `feat/game-mvp-backend` (deployed via supabase CLI, not merged to main). The frontend `index.html` lives on `main` (deployed via Cloudflare Pages).

- **Tasks 1–2** (function code + tests) → do on `feat/game-mvp-backend`.
- **Task 3** (`index.html`) → do on `main`.

Switch branches exactly as each task says. Do not mix.

## Prerequisite: Deno

Tasks 1–2 run Deno tests / type-checks. Deno is not on PATH in this environment. Install once (free, local, no cost):

```bash
# Windows PowerShell:
winget install DenoLand.Deno
#   …or:  irm https://deno.land/install.ps1 | iex
deno --version   # confirm it prints a version
```

If Deno truly cannot be installed, the pure function in Task 1 is plain TS with no Deno-specific runtime calls — the tests can alternatively be run by porting the three `Deno.test(...)` wrappers to any TS test runner. Prefer Deno to match the existing `game_logic_test.ts`.

## File structure

- **Create** `supabase/functions/_shared/skill_board.ts` — pure aggregation: raw rows → ranked board + caller row. One responsibility, no I/O, fully testable. (branch `feat/game-mvp-backend`)
- **Create** `supabase/functions/_shared/skill_board_test.ts` — Deno unit tests for the above. (branch `feat/game-mvp-backend`)
- **Modify** `supabase/functions/game-leaderboard/index.ts` — add the `type=skill` branch that fetches rows and delegates to `buildSkillBoard`. (branch `feat/game-mvp-backend`)
- **Modify** `index.html` — toggle gains `🎯 Win vs AI`, default first load, skill render path + pin-my-rank. (branch `main`)

---

### Task 1: Pure aggregation function `buildSkillBoard` (TDD)

**Files:**
- Create: `supabase/functions/_shared/skill_board.ts`
- Test: `supabase/functions/_shared/skill_board_test.ts`

**Branch:** `feat/game-mvp-backend`

- [ ] **Step 1: Switch to the backend branch**

```bash
git checkout feat/game-mvp-backend
```
Expected: "Switched to branch 'feat/game-mvp-backend'".

- [ ] **Step 2: Write the failing test file**

Create `supabase/functions/_shared/skill_board_test.ts`:

```ts
// supabase/functions/_shared/skill_board_test.ts
import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { buildSkillBoard, SKILL_MIN_ROUNDS } from "./skill_board.ts";

const players = [
  { id: "a", display_name: "Alice", level: 3 },
  { id: "b", display_name: "Bob", level: 2 },
  { id: "c", display_name: "Cara", level: 1 },
];
// helper: one daily_result row (defaults: 1 correct pick of 3)
function rr(player_id: string, beat_ai: boolean, correct_count = 1, picks_count = 3) {
  return { player_id, beat_ai, correct_count, picks_count };
}

Deno.test("SKILL_MIN_ROUNDS is 3", () => {
  assertEquals(SKILL_MIN_ROUNDS, 3);
});

Deno.test("gate: <3 rounds excluded, >=3 included", () => {
  const results = [
    rr("a", true), rr("a", true), rr("a", false), // 3 rounds, 2 wins → 67%
    rr("b", true), rr("b", true),                  // 2 rounds → excluded
  ];
  const { rows } = buildSkillBoard(results, players, { limit: 20 });
  assertEquals(rows.length, 1);
  assertEquals(rows[0].display_name, "Alice");
  assertEquals(rows[0].win_rate, 67); // round(2/3*100)
  assertEquals(rows[0].wins, 2);
  assertEquals(rows[0].rounds, 3);
  assertEquals(rows[0].is_ai, false);
});

Deno.test("sort by win_rate desc", () => {
  const results = [
    rr("a", true), rr("a", true), rr("a", true),    // 100%
    rr("b", true), rr("b", false), rr("b", false),  // 33%
  ];
  const { rows } = buildSkillBoard(results, players, { limit: 20 });
  assertEquals(rows.map((r) => r.display_name), ["Alice", "Bob"]);
  assertEquals(rows[0].win_rate, 100);
  assertEquals(rows[1].win_rate, 33);
  assertEquals(rows[0].rank, 1);
  assertEquals(rows[1].rank, 2);
});

Deno.test("tiebreak: equal win_rate -> higher accuracy first", () => {
  const results = [
    rr("a", true, 3, 3), rr("a", true, 2, 3), rr("a", false, 1, 3), // 2/3 win, acc 6/9=67%
    rr("b", true, 1, 3), rr("b", true, 1, 3), rr("b", false, 1, 3), // 2/3 win, acc 3/9=33%
  ];
  const { rows } = buildSkillBoard(results, players, { limit: 20 });
  assertEquals(rows.map((r) => r.display_name), ["Alice", "Bob"]);
  assertEquals(rows[0].win_rate, 67);
  assertEquals(rows[1].win_rate, 67);
  assertEquals(rows[0].accuracy, 67);
  assertEquals(rows[1].accuracy, 33);
});

Deno.test("tiebreak: equal win_rate & accuracy -> more rounds first", () => {
  const results = [
    ...Array(6).fill(0).map((_, i) => rr("a", i < 4, 2, 3)), // 6 rounds, 4 wins=67%, acc 12/18=67%
    ...Array(3).fill(0).map((_, i) => rr("b", i < 2, 2, 3)), // 3 rounds, 2 wins=67%, acc 6/9=67%
  ];
  const { rows } = buildSkillBoard(results, players, { limit: 20 });
  assertEquals(rows.map((r) => r.display_name), ["Alice", "Bob"]);
  assertEquals(rows[0].rounds, 6);
  assertEquals(rows[1].rounds, 3);
});

Deno.test("me: below gate -> rank null, needs = remaining", () => {
  const results = [rr("c", true), rr("c", false)]; // Cara: 2 rounds
  const { me } = buildSkillBoard(results, players, { limit: 20, mePlayerId: "c" });
  assertEquals(me?.rank, null);
  assertEquals(me?.rounds, 2);
  assertEquals(me?.needs, 1); // 3 - 2
  assertEquals(me?.display_name, "Cara");
});

Deno.test("me: qualified -> real rank, needs 0", () => {
  const results = [
    rr("a", true), rr("a", true), rr("a", true),    // Alice 100% rank 1
    rr("c", true), rr("c", false), rr("c", false),  // Cara 33% rank 2
  ];
  const { me } = buildSkillBoard(results, players, { limit: 20, mePlayerId: "c" });
  assertEquals(me?.rank, 2);
  assertEquals(me?.needs, 0);
  assertEquals(me?.win_rate, 33);
});

Deno.test("empty input -> no rows; me with no history needs full gate", () => {
  const { rows, me } = buildSkillBoard([], players, { limit: 20, mePlayerId: "a" });
  assertEquals(rows.length, 0);
  assertEquals(me?.rank, null);
  assertEquals(me?.rounds, 0);
  assertEquals(me?.needs, 3);
});

Deno.test("limit caps rows but rank is global", () => {
  const results = [
    rr("a", true), rr("a", true), rr("a", true),     // 100% rank1
    rr("b", true), rr("b", true), rr("b", false),    // 67%  rank2
    rr("c", true), rr("c", false), rr("c", false),   // 33%  rank3
  ];
  const { rows } = buildSkillBoard(results, players, { limit: 2 });
  assertEquals(rows.length, 2);
  assertEquals(rows[1].rank, 2);
});
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
deno test supabase/functions/_shared/skill_board_test.ts
```
Expected: FAIL — module `./skill_board.ts` not found / `buildSkillBoard` is not exported.

- [ ] **Step 4: Implement `skill_board.ts`**

Create `supabase/functions/_shared/skill_board.ts`:

```ts
// supabase/functions/_shared/skill_board.ts
// Pure aggregation for the "Win vs AI" skill leaderboard.
// Ranks human players by beat-AI win rate; accuracy is a column + tiebreaker.
// No I/O — caller supplies raw rows so this is fully unit-testable.

export const SKILL_MIN_ROUNDS = 3;

export interface SkillResultRow {
  player_id: string;
  beat_ai: boolean;
  correct_count: number;
  picks_count: number;
}
export interface SkillPlayer {
  id: string;
  display_name: string | null;
  level: number | null;
}
export interface SkillRow {
  rank: number;
  is_ai: false;
  display_name: string;
  level: number;
  win_rate: number; // 0..100, integer
  accuracy: number; // 0..100, integer
  wins: number;
  rounds: number;
}
export interface SkillMe {
  rank: number | null; // null when below the gate
  display_name: string;
  win_rate: number;
  accuracy: number;
  wins: number;
  rounds: number;
  needs: number; // rounds still required to qualify (0 once qualified)
}
export interface SkillBoard {
  rows: SkillRow[];
  me: SkillMe | null;
}

interface Agg { rounds: number; wins: number; correct: number; picks: number; }

const winRateOf = (a: Agg): number => Math.round((a.wins / a.rounds) * 100);
const accuracyOf = (a: Agg): number => (a.picks > 0 ? Math.round((a.correct / a.picks) * 100) : 0);

export function buildSkillBoard(
  results: SkillResultRow[],
  players: SkillPlayer[],
  opts: { limit: number; mePlayerId?: string | null },
): SkillBoard {
  // 1. aggregate per player
  const agg = new Map<string, Agg>();
  for (const r of results) {
    const a = agg.get(r.player_id) ?? { rounds: 0, wins: 0, correct: 0, picks: 0 };
    a.rounds += 1;
    if (r.beat_ai) a.wins += 1;
    a.correct += r.correct_count;
    a.picks += r.picks_count;
    agg.set(r.player_id, a);
  }

  // 2. player lookup
  const pmap = new Map<string, SkillPlayer>();
  for (const p of players) pmap.set(p.id, p);

  // 3. qualified entries (rounds >= gate)
  const entries = [...agg.entries()]
    .filter(([, a]) => a.rounds >= SKILL_MIN_ROUNDS)
    .map(([pid, a]) => ({
      pid,
      name: pmap.get(pid)?.display_name || "Trader",
      level: pmap.get(pid)?.level || 1,
      win_rate: winRateOf(a),
      accuracy: accuracyOf(a),
      wins: a.wins,
      rounds: a.rounds,
    }));

  // 4. sort: win_rate desc, accuracy desc, rounds desc, pid asc (deterministic)
  entries.sort((x, y) =>
    y.win_rate - x.win_rate ||
    y.accuracy - x.accuracy ||
    y.rounds - x.rounds ||
    (x.pid < y.pid ? -1 : x.pid > y.pid ? 1 : 0)
  );

  // 5. assign global ranks, then slice to limit
  const ranked = entries.map((e, i) => ({ ...e, rank: i + 1 }));
  const rows: SkillRow[] = ranked.slice(0, opts.limit).map((e) => ({
    rank: e.rank,
    is_ai: false,
    display_name: e.name,
    level: e.level,
    win_rate: e.win_rate,
    accuracy: e.accuracy,
    wins: e.wins,
    rounds: e.rounds,
  }));

  // 6. caller row (pin-my-rank / gate prompt)
  let me: SkillMe | null = null;
  const mePid = opts.mePlayerId;
  if (mePid) {
    const a = agg.get(mePid);
    const rounds = a?.rounds ?? 0;
    const name = pmap.get(mePid)?.display_name || "You";
    if (a && rounds >= SKILL_MIN_ROUNDS) {
      const entry = ranked.find((e) => e.pid === mePid)!;
      me = {
        rank: entry.rank, display_name: name,
        win_rate: entry.win_rate, accuracy: entry.accuracy,
        wins: entry.wins, rounds: entry.rounds, needs: 0,
      };
    } else {
      me = {
        rank: null, display_name: name,
        win_rate: a ? winRateOf(a) : 0,
        accuracy: a ? accuracyOf(a) : 0,
        wins: a?.wins ?? 0, rounds,
        needs: SKILL_MIN_ROUNDS - rounds,
      };
    }
  }

  return { rows, me };
}
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
deno test supabase/functions/_shared/skill_board_test.ts
```
Expected: PASS — all tests green (9 passed).

- [ ] **Step 6: Commit**

```bash
git add supabase/functions/_shared/skill_board.ts supabase/functions/_shared/skill_board_test.ts
git commit -m "feat(game): pure beat-AI skill leaderboard aggregation + tests"
```

---

### Task 2: Wire `type=skill` into the leaderboard function

**Files:**
- Modify: `supabase/functions/game-leaderboard/index.ts`

**Branch:** `feat/game-mvp-backend` (continue from Task 1)

- [ ] **Step 1: Add the import**

At the top of `supabase/functions/game-leaderboard/index.ts`, below the existing `createClient` import, add:

```ts
import { buildSkillBoard } from "../_shared/skill_board.ts";
```

- [ ] **Step 2: Accept `skill` as a valid type**

Find this line near the top of the handler:

```ts
    const type = url.searchParams.get("type") === "xp" ? "xp" : "return";
```

Replace it with:

```ts
    const typeParam = url.searchParams.get("type");
    const type = typeParam === "xp" ? "xp" : typeParam === "skill" ? "skill" : "return";
```

- [ ] **Step 3: Add the skill branch**

Insert the following block **immediately after** the closing `}` of the `if (type === "xp") { … }` block and **before** the `// ===== RETURN BOARD` comment:

```ts
    // ===== SKILL BOARD (beat-AI win rate, players only) =====
    if (type === "skill") {
      const { data: results } = await supabase.from("game_daily_result")
        .select("player_id, beat_ai, correct_count, picks_count");
      const { data: players } = await supabase.from("players")
        .select("id, display_name, level");

      let mePlayerId: string | null = null;
      if (deviceId) {
        const { data: meP } = await supabase.from("players")
          .select("id").eq("device_id", deviceId).maybeSingle();
        mePlayerId = meP?.id ?? null;
      }

      const { rows, me } = buildSkillBoard(
        (results ?? []) as any,
        (players ?? []) as any,
        { limit, mePlayerId },
      );

      const { count: aiCount } = await supabase.from("agents")
        .select("id", { count: "exact", head: true })
        .or("game_roster.eq.true,game_external.eq.true");

      return new Response(
        JSON.stringify({ success: true, type, rows, ai_total: aiCount ?? 0, me, season: null }),
        { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }
```

- [ ] **Step 4: Type-check the function**

```bash
deno check supabase/functions/game-leaderboard/index.ts
```
Expected: no errors (exit 0). If Deno reports type errors, fix them before continuing.

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/game-leaderboard/index.ts
git commit -m "feat(game): add type=skill branch to game-leaderboard"
```

> **Deploy is a separate, owner-approved step** (supabase CLI). Do not deploy as part of this task. After the whole plan is implemented and reviewed, the deploy + curl smoke (`?type=skill`) happens at the rollout gate.

---

### Task 3: Frontend — `🎯 Win vs AI` toggle, default tab, render

**Files:**
- Modify: `index.html` (game leaderboard widget: lines ~6290 and ~6570–6604)

**Branch:** `main`

- [ ] **Step 1: Switch to main**

```bash
git checkout main
```
Expected: "Switched to branch 'main'". (Task 1–2 commits stay on the backend branch.)

- [ ] **Step 2: Make skill the default first load**

In `index.html`, find (around line 6290):

```js
      gmLoadLeaderboard('return');
```
Replace with:

```js
      gmLoadLeaderboard('skill');
```

- [ ] **Step 3: Add the skill toggle button (default `on`)**

Find the toggle markup inside `window.gmLoadLeaderboard` (line ~6572). Replace this fragment:

```js
<div class="gm-lbtog"><button id="gmlb-return" class="'+(type==='return'?'on':'')+'" onclick="gmLoadLeaderboard(\'return\')">💰 Return</button><button id="gmlb-xp" class="'+(type==='xp'?'on':'')+'" onclick="gmLoadLeaderboard(\'xp\')">🏆 Season</button></div>
```

with (adds the skill button first):

```js
<div class="gm-lbtog"><button id="gmlb-skill" class="'+(type==='skill'?'on':'')+'" onclick="gmLoadLeaderboard(\'skill\')">🎯 Win vs AI</button><button id="gmlb-return" class="'+(type==='return'?'on':'')+'" onclick="gmLoadLeaderboard(\'return\')">💰 Return</button><button id="gmlb-xp" class="'+(type==='xp'?'on':'')+'" onclick="gmLoadLeaderboard(\'xp\')">🏆 Season</button></div>
```

- [ ] **Step 4: Add the skill render + pin-my-rank path**

In the same function, find the `try{ … }` body that fetches and renders. Immediately **after** this line:

```js
        const aiTotal=Number(d.ai_total)||0;
```

insert the entire skill branch (it renders and returns, leaving the existing return/xp code untouched):

```js
        if(type==='skill'){
          const SKILL_MIN=3;
          let shdr=(aiTotal>0)?('<div class="gm-lb-aihdr">🤖 '+aiTotal+' AI rival'+(aiTotal===1?'':'s')+' — beat them</div>'):'';
          const sme=d.me; let smeHtml='';
          if(sme){
            if(sme.needs>0){
              smeHtml='<div class="gm-lb-mediv">⋯</div><div class="gm-muted" style="text-align:center">Play '+sme.needs+' more round'+(sme.needs===1?'':'s')+' to appear here.</div>';
            } else if(sme.rank>rows.length){
              smeHtml='<div class="gm-lb-mediv">⋯</div><div class="gm-lbrow gm-lb-me"><span class="rk">'+sme.rank+'</span><span class="nm">🧑‍💻 '+(sme.display_name||'You')+' <span style="color:#8b949e;font-size:11px">YOU</span></span><span class="vl">🆚 '+sme.win_rate+'% · 🎯 '+sme.accuracy+'%</span></div>';
            }
          }
          const sbody = rows.length ? (shdr + rows.map(x=>{
            var nmCls=gmNameClass(x.level);
            return '<div class="gm-lbrow"><span class="rk">'+x.rank+'</span><span class="nm '+nmCls+'">'+(GM_BADGES[(x.level||1)-1]||'🐣')+' '+(x.display_name||'Trader')+' <span style="color:#8b949e;font-size:11px">Lv.'+x.level+'</span></span><span class="vl">🆚 '+x.win_rate+'% <span style="color:#8b949e;font-size:11px">('+x.wins+'/'+x.rounds+')</span> · 🎯 '+x.accuracy+'%</span></div>';
          }).join('') + smeHtml) : (shdr + '<div class="gm-muted">Win vs the AI in '+SKILL_MIN+' rounds to claim the top skill rank.</div>' + smeHtml);
          const sel=document.getElementById('gm-lb-rows'); if(sel) sel.innerHTML=sbody;
          return;
        }
```

- [ ] **Step 5: Manual verification (no automated FE test exists)**

Because the change is inside a string-built widget, verify by reading the diff and (if possible) loading the page:

```bash
git diff index.html
```
Confirm in the diff:
1. Line ~6290 now calls `gmLoadLeaderboard('skill')`.
2. The toggle has three buttons, `🎯 Win vs AI` first with `id="gmlb-skill"`.
3. The `if(type==='skill'){ … return; }` block is present and ends with `return;` so the existing return/xp render below is not reached for skill.

If a local/staged Cloudflare preview is available, open the game page and check: leaderboard opens on `🎯 Win vs AI`; rows show `🆚 N% (w/r) · 🎯 N%`; switching to Return/Season still works.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "feat(game): Win vs AI skill leaderboard tab (default) in UI"
```

> **Deploy is a separate, owner-approved step** (push `main` → Cloudflare). Not part of this task.

---

## Rollout (owner-approved gates, AFTER all tasks + review)

1. **Deploy `game-leaderboard`** from `feat/game-mvp-backend` via supabase CLI. Smoke:
   `GET …/functions/v1/game-leaderboard?type=skill&limit=20` returns `success:true, type:"skill"`
   with qualified rows (or empty `rows` if nobody has 3+ rounds yet); confirm `?type=return` and
   `?type=xp` still behave exactly as before.
2. **Push `index.html`** on `main` → Cloudflare. Verify on the live site: leaderboard opens on
   `🎯 Win vs AI`; rows show `🆚 %` and `🎯 %`; a sub-3-round device sees "Play N more rounds";
   Return/Season tabs unchanged.

## Self-review (completed by plan author)

- **Spec coverage:** metric/win-rate (Task 1) · accuracy column + tiebreak ①②③ (Task 1 tests + impl) · 3-round gate (Task 1) · lifetime scope (Task 2 fetches all rows) · players-only/bots-excluded (Task 1 has no AI path; Task 2 queries players) · default tab + toggle (Task 3 steps 2–3) · `type=skill` branch / no DB change (Task 2) · pin-my-rank + needs prompt (Task 1 `me`, Task 3 step 4) · empty-state copy (Task 3 step 4) · rollout smoke (Rollout). All covered.
- **Placeholder scan:** none — every code step shows full code; no TBD/TODO.
- **Type consistency:** `buildSkillBoard(results, players, {limit, mePlayerId})` signature and the `win_rate/accuracy/wins/rounds/needs/rank` field names are identical across Task 1 impl, Task 1 tests, Task 2 call site, and Task 3 render. `SKILL_MIN_ROUNDS` (backend) vs local `SKILL_MIN=3` (frontend copy constant) — intentional, both = 3.

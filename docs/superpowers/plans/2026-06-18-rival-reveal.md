# Rival Reveal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reveal the daily AI rival as a named character with persona (pick → live → result) and turn the result card into a scoreboard showing both returns and the %p margin.

**Architecture:** A pure formatter (`_shared/rival_result.ts`, Deno-tested) turns a result row into display strings. `game-state` joins `agents` (name/persona only) to expose `today_rival` and enrich `last_result` with rival name/persona + the formatted scoreboard. `index.html` renders a rival banner on the pick/live cards and a scoreboard on the result card. No DB schema change, no XP change.

**Tech Stack:** Deno / TypeScript (Supabase Edge Functions), vanilla JS in `index.html`, Deno std `assertEquals` for tests.

**Spec:** `docs/superpowers/specs/2026-06-18-rival-reveal-design.md`

---

## Branch strategy (read first)

- **Tasks 1–2** (function code + tests) → branch `feat/game-mvp-backend`.
- **Task 3** (`index.html`) → branch `main`.

The controller switches branches between tasks. Each task below states its branch and assumes it is already checked out — do NOT run `git checkout` inside a task.

## Prerequisite: Deno

Tasks 1–2 run Deno. Deno is not on PATH — use the full path in every command:
`/c/Users/amire/.deno/bin/deno.exe` (confirmed deno 2.8.2).

## File structure

- **Create** `supabase/functions/_shared/rival_result.ts` — pure formatter: result row → display strings. (feat branch)
- **Create** `supabase/functions/_shared/rival_result_test.ts` — Deno unit tests. (feat branch)
- **Modify** `supabase/functions/game-state/index.ts` — add `today_rival` + enrich `last_result`. (feat branch)
- **Modify** `index.html` — `gmEsc` helper, `gmTodayRival` global, rival banner on pick/live cards, scoreboard on result card. (main branch)

---

### Task 1: Pure formatter `formatRivalResult` (TDD)

**Files:**
- Create: `supabase/functions/_shared/rival_result.ts`
- Test: `supabase/functions/_shared/rival_result_test.ts`

**Branch:** `feat/game-mvp-backend`

- [ ] **Step 1: Write the test file** `supabase/functions/_shared/rival_result_test.ts`:

```ts
// supabase/functions/_shared/rival_result_test.ts
import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { formatRivalResult } from "./rival_result.ts";

Deno.test("win: verdict BEAT name, positive margin", () => {
  const d = formatRivalResult({ rival_name: "BearBot-EN", my_return: 2.04, ai_return: 1.52, beat_ai: true });
  assertEquals(d.has_scoreboard, true);
  assertEquals(d.verdict, "🏆 BEAT BearBot-EN");
  assertEquals(d.you_pct, "+2.04%");
  assertEquals(d.rival_pct, "+1.52%");
  assertEquals(d.margin, "(+0.52%p)");
});

Deno.test("loss: verdict Lost, negative margin with unicode minus", () => {
  const d = formatRivalResult({ rival_name: "BearBot-EN", my_return: 1.52, ai_return: 2.04, beat_ai: false });
  assertEquals(d.verdict, "😖 Lost this time");
  assertEquals(d.margin, "(−0.52%p)");
});

Deno.test("negative returns format with sign", () => {
  const d = formatRivalResult({ rival_name: "X", my_return: -1.5, ai_return: -0.5, beat_ai: false });
  assertEquals(d.you_pct, "-1.50%");
  assertEquals(d.rival_pct, "-0.50%");
  assertEquals(d.margin, "(−1.00%p)");
});

Deno.test("tie: margin 0.00, verdict follows beat_ai flag", () => {
  const d = formatRivalResult({ rival_name: "X", my_return: 1.0, ai_return: 1.0, beat_ai: false });
  assertEquals(d.margin, "(+0.00%p)");
  assertEquals(d.verdict, "😖 Lost this time");
});

Deno.test("missing rival_name -> legacy fallback, no scoreboard", () => {
  const d = formatRivalResult({ rival_name: null, my_return: 1.0, ai_return: 0.5, beat_ai: true });
  assertEquals(d.has_scoreboard, false);
  assertEquals(d.verdict, "🏆 BEAT THE AI");
});

Deno.test("missing ai_return -> legacy fallback", () => {
  const d = formatRivalResult({ rival_name: "X", my_return: 1.0, ai_return: null, beat_ai: false });
  assertEquals(d.has_scoreboard, false);
  assertEquals(d.verdict, "Lost this time");
});
```

- [ ] **Step 2: Run the test, confirm it FAILS** (module not found):

```
/c/Users/amire/.deno/bin/deno.exe test supabase/functions/_shared/rival_result_test.ts
```
Expected: failure — cannot find `./rival_result.ts`.

- [ ] **Step 3: Implement** `supabase/functions/_shared/rival_result.ts`:

```ts
// supabase/functions/_shared/rival_result.ts
// Pure formatter: a resolved result row -> display strings for the duel scoreboard.
// No I/O, no DOM. Falls back to legacy "BEAT THE AI / Lost this time" text when the
// rival name or the AI return is missing (old rows).

export interface RivalResultInput {
  rival_name: string | null;
  my_return: number | null; // game_daily_result.avg_return_pct
  ai_return: number | null; // game_daily_result.ai_avg_return_pct
  beat_ai: boolean;
}
export interface RivalResultDisplay {
  has_scoreboard: boolean;
  rival_name: string;
  you_pct: string;   // e.g. "+2.04%"
  rival_pct: string; // e.g. "+1.52%"
  verdict: string;   // e.g. "🏆 BEAT BearBot-EN" / "😖 Lost this time"
  margin: string;    // e.g. "(+0.52%p)" / "(−0.52%p)"
}

function pctStr(n: number): string {
  return (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
}

export function formatRivalResult(input: RivalResultInput): RivalResultDisplay {
  const { rival_name, my_return, ai_return, beat_ai } = input;
  if (rival_name == null || my_return == null || ai_return == null) {
    return {
      has_scoreboard: false,
      rival_name: "",
      you_pct: "",
      rival_pct: "",
      verdict: beat_ai ? "🏆 BEAT THE AI" : "Lost this time",
      margin: "",
    };
  }
  const m = Math.round((my_return - ai_return) * 100) / 100;
  const margin = "(" + (m >= 0 ? "+" : "−") + Math.abs(m).toFixed(2) + "%p)";
  return {
    has_scoreboard: true,
    rival_name,
    you_pct: pctStr(my_return),
    rival_pct: pctStr(ai_return),
    verdict: beat_ai ? "🏆 BEAT " + rival_name : "😖 Lost this time",
    margin,
  };
}
```

- [ ] **Step 4: Run the test, confirm ALL PASS:**

```
/c/Users/amire/.deno/bin/deno.exe test supabase/functions/_shared/rival_result_test.ts
```
Expected: 6 tests pass.

- [ ] **Step 5: Commit:**

```
git add supabase/functions/_shared/rival_result.ts supabase/functions/_shared/rival_result_test.ts
git commit -m "feat(game): pure rival-result scoreboard formatter + tests"
```

---

### Task 2: Expose rival in `game-state`

**Files:**
- Modify: `supabase/functions/game-state/index.ts`

**Branch:** `feat/game-mvp-backend`

Context: the handler already has `const today = todayUtc();` and
`const { data: lastResult } = await supabase.from("game_daily_result").select("*")…maybeSingle();`,
then builds a `return new Response(JSON.stringify({ success, player, submitted_today,
last_result: lastResult ?? null, current_season }) …)`.

- [ ] **Step 1: Add the import** at the top of `supabase/functions/game-state/index.ts`, below the existing `createClient` import:

```ts
import { formatRivalResult } from "../_shared/rival_result.ts";
```

- [ ] **Step 2: Add rival lookups** — insert this block immediately AFTER the `lastResult` query line (`…order("trade_date", { ascending: false }).limit(1).maybeSingle();`) and BEFORE the `const { data: season }` line:

```ts
    // today's rival (name + persona only — never claim_token)
    const { data: rivalRow } = await supabase.from("game_daily_rival")
      .select("agent_id").eq("trade_date", today).maybeSingle();
    let today_rival: { name: string; persona: string | null } | null = null;
    if (rivalRow?.agent_id) {
      const { data: ag } = await supabase.from("agents")
        .select("name, persona").eq("id", rivalRow.agent_id).maybeSingle();
      if (ag) today_rival = { name: ag.name, persona: ag.persona };
    }

    // enrich last_result with rival name/persona + formatted scoreboard
    let last_result: any = lastResult ?? null;
    if (last_result) {
      let rival_name: string | null = null;
      let rival_persona: string | null = null;
      if (last_result.ai_agent_id) {
        const { data: lrAg } = await supabase.from("agents")
          .select("name, persona").eq("id", last_result.ai_agent_id).maybeSingle();
        if (lrAg) { rival_name = lrAg.name; rival_persona = lrAg.persona; }
      }
      const rival_display = formatRivalResult({
        rival_name,
        my_return: last_result.avg_return_pct ?? null,
        ai_return: last_result.ai_avg_return_pct ?? null,
        beat_ai: !!last_result.beat_ai,
      });
      last_result = { ...last_result, rival_name, rival_persona, rival_display };
    }
```

- [ ] **Step 3: Update the response** — change the returned object's `last_result` to use the enriched variable and add `today_rival`. Replace:

```ts
      last_result: lastResult ?? null,
      current_season,
```
with:

```ts
      last_result,
      today_rival,
      current_season,
```

- [ ] **Step 4: Type-check:**

```
/c/Users/amire/.deno/bin/deno.exe check supabase/functions/game-state/index.ts
```
Expected: no errors (exit 0). Fix any type errors minimally; do not change other behavior.

- [ ] **Step 5: Commit:**

```
git add supabase/functions/game-state/index.ts
git commit -m "feat(game): expose today_rival + rival scoreboard in game-state"
```

> Deploy is a separate owner-approved step. Do NOT deploy in this task.

---

### Task 3: Frontend — rival banner + result scoreboard

**Files:**
- Modify: `index.html`

**Branch:** `main`

- [ ] **Step 1: Add an HTML-escape helper + the rival global.** Find the `gmSeason` declaration (line ~5956: `let gmSeason = null;`). Insert immediately after it:

```js
    let gmTodayRival = null;  // {name, persona} from game-state, for the rival banner
    function gmEsc(s){ return String(s==null?'':s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
    function gmRivalLine(){
      if(!gmTodayRival){ return '<div class="gm-vssum">⚔️ Today\'s rival posts at the open.</div>'; }
      var p=(gmTodayRival.persona||'').trim(); if(p.length>60) p=p.slice(0,57)+'…';
      return '<div class="gm-vssum">⚔️ Today\'s rival: <b>'+gmEsc(gmTodayRival.name)+'</b>'+(p?' · '+gmEsc(p):'')+'</div>';
    }
```

- [ ] **Step 2: Store the rival from game-state.** In the page-load function, find the line `gmSeason = state.current_season || null;` (around line 6285). Insert immediately after it:

```js
      gmTodayRival = state.today_rival || null;
```

- [ ] **Step 3: Reveal the rival on the locked pick card.** Find this exact block (around line 6519, the `if(submitted){ … }` inside the PICK phase) — note the "rival stays hidden" copy:

```js
        box.innerHTML=banner
          +'<h3 style="margin-top:12px">✅ Locked in!</h3>'
          +rows
          +'<div class="gm-vssum">Your rival stays hidden until the bell. Watch the <b>⚡ live race vs the AI</b> when the market opens at 9:30 AM ET.</div>';
        return;
```
Replace it with (reveals identity; bot's picks still appear only after the bell):

```js
        box.innerHTML=banner
          +'<h3 style="margin-top:12px">✅ Locked in!</h3>'
          +rows
          +gmRivalLine()
          +'<div class="gm-vssum">Their picks stay hidden until the bell — watch the <b>⚡ live race vs the AI</b> when the market opens at 9:30 AM ET.</div>';
        return;
```

- [ ] **Step 4: Name the rival on the live card.** Find this exact line (around line 6489):

```js
            +'<div><span class="lbl">AI rival</span><span class="'+(aiAgg==null?'gm-muted':cls(aiAgg))+'" style="font-weight:800">'+(aiAgg==null?'—':pct(aiAgg))+'</span></div></div>'
```
Replace `AI rival` with the rival name when known:

```js
            +'<div><span class="lbl">'+(gmTodayRival?gmEsc(gmTodayRival.name):'AI rival')+'</span><span class="'+(aiAgg==null?'gm-muted':cls(aiAgg))+'" style="font-weight:800">'+(aiAgg==null?'—':pct(aiAgg))+'</span></div></div>'
```

- [ ] **Step 5: Scoreboard on the result card.** In `gmRenderResult(res)` (around line 6413), find this exact line:

```js
        +'<div class="gm-rrow"><span class="k">vs AI</span><span>'+(res.beat_ai?'<span class="gm-beat">🏆 BEAT THE AI</span>':'Lost this time')+'</span></div>'
```
Replace it with a scoreboard built from `res.rival_display` (falls back to the old row when there's no scoreboard):

```js
        +(function(){
           var rd=res.rival_display;
           if(rd && rd.has_scoreboard){
             return '<div class="gm-rrow"><span class="k">⚔️ Rival</span><span style="font-weight:800">'+gmEsc(rd.rival_name)+'</span></div>'
               +(res.rival_persona?'<div class="gm-rrow"><span class="k"></span><span class="gm-muted" style="font-size:12px">'+gmEsc(res.rival_persona)+'</span></div>':'')
               +'<div class="gm-rrow"><span class="k">You</span><span style="font-weight:800">'+rd.you_pct+'</span></div>'
               +'<div class="gm-rrow"><span class="k">'+gmEsc(rd.rival_name)+'</span><span style="font-weight:800">'+rd.rival_pct+'</span></div>'
               +'<div class="gm-rrow"><span class="k">Result</span><span>'+(res.beat_ai?'<span class="gm-beat">'+gmEsc(rd.verdict)+'</span>':gmEsc(rd.verdict))+' <span class="gm-muted" style="font-size:12px">'+rd.margin+'</span></span></div>';
           }
           return '<div class="gm-rrow"><span class="k">vs AI</span><span>'+(res.beat_ai?'<span class="gm-beat">🏆 BEAT THE AI</span>':'Lost this time')+'</span></div>';
         })()
```

- [ ] **Step 6: Manual verification.** Run:

```
git diff index.html
```
Confirm:
1. `gmEsc`, `gmRivalLine`, and `let gmTodayRival` added near line ~5956.
2. `gmTodayRival = state.today_rival || null;` added after the `gmSeason =` line.
3. Pick card now calls `gmRivalLine()` and says "Their picks stay hidden until the bell".
4. Live card label uses `gmTodayRival.name` when present.
5. Result card has the `res.rival_display` scoreboard branch with a legacy fallback.

The inserted blocks use single-quoted strings matching the surrounding style; visually confirm quote/paren balance (especially the IIFE in Step 5 closes with `})()`).

- [ ] **Step 7: Commit:**

```
git add index.html
git commit -m "feat(game): reveal rival name/persona + result scoreboard in UI"
```

> Deploy is a separate owner-approved step. Do NOT deploy/push in this task.

---

## Rollout (owner-approved, BACKEND FIRST)

1. **Deploy `game-state`** from `feat/game-mvp-backend` (supabase CLI). Smoke:
   `POST …/functions/v1/game-state` with a device_id that has a resolved round → response has
   `last_result.rival_name`, `last_result.rival_display`, and `today_rival` (when a daily rival
   exists). **Confirm `claim_token` appears nowhere in the JSON.**
2. **Push `index.html`** on `main` → Cloudflare. Verify on the live game page: locked pick card
   shows "Today's rival: <name>"; result card shows the You/rival scoreboard with the `%p` margin;
   live card (during market hours) shows the rival's name.

Backend-first matters: if the frontend ships first, `today_rival`/`rival_display` are absent →
banner falls back to "posts at the open" and the result card uses the legacy row (no crash, but no
new info) until the function catches up.

## Self-review (completed by plan author)

- **Spec coverage:** name+persona reveal from pick stage (Task 3 step 3) · identity early / picks
  still locked (step 3 copy + no change to ai_pick gating) · backend join name/persona only, no
  claim_token (Task 2 selects `name, persona`) · result scoreboard with margin (Task 1 formatter +
  Task 3 step 5) · today_rival + last_result fields (Task 2) · live card name (step 4) · legacy
  fallback (formatter + step 5) · pure formatter unit-tested (Task 1) · English text · no DB/XP
  change. All covered. (Per-bot record + pick pre-reveal correctly excluded.)
- **Placeholder scan:** none — all code steps show full code.
- **Type/name consistency:** `formatRivalResult` input `{rival_name, my_return, ai_return,
  beat_ai}` and output `{has_scoreboard, rival_name, you_pct, rival_pct, verdict, margin}` are
  identical across Task 1 impl, Task 1 tests, and Task 2 call site. Frontend reads
  `res.rival_display.{has_scoreboard,rival_name,you_pct,rival_pct,verdict,margin}`,
  `res.rival_name`, `res.rival_persona`, `state.today_rival.{name,persona}` — all produced by
  Task 2. Consistent.

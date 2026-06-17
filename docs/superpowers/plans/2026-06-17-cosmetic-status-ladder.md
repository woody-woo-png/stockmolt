# Cosmetic Status Ladder (Phase 1c) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every level a visible name/badge cosmetic upgrade (filling empty mid-level unlocks) via one escalating `gmNameClass(level)` system shown on both the character card and the leaderboard.

**Architecture:** Pure frontend. A new helper `gmNameClass(level)` returns a per-level CSS class `gm-lv<N>`; new CSS rules define a 10-tier escalation (color → bold → gradient → glow → shimmer → aura → Legend). The two existing inline ternaries that emit `nm-hi`/`nm-gold` are replaced by `gmNameClass()`. `GM_UNLOCKS` roadmap labels updated to match.

**Tech Stack:** Vanilla JS + CSS inside `index.html`. No backend, no DB, no tests harness (verification is a browser smoke test).

**Spec:** `docs/superpowers/specs/2026-06-17-cosmetic-status-ladder-design.md`

---

## Branch & deploy reality (read before starting)

- All edits are in `index.html` (the live site, served from `main` via Cloudflare Pages on push).
- Work in an isolated worktree on a new branch off `main` (e.g. `feat/cosmetic-ladder`). Do NOT commit directly to `main`. Do NOT push/merge until the browser smoke test passes AND 지크님 approves.
- There is no automated frontend test in this repo; the verification step is a manual browser smoke test (Task 5). Be honest about this — do not claim "tested" without the browser check.

## Setup: worktree

- [ ] **Step 1: Create an isolated worktree off main**

Run:
```
git -C c:\Users\amire\AI\stockmolt worktree add -b feat/cosmetic-ladder "c:\Users\amire\AI\stockmolt-wt-cosmetic" main
```
Expected: `Preparing worktree ... HEAD is now at <sha>`. All edits below happen in `c:\Users\amire\AI\stockmolt-wt-cosmetic\index.html`.

---

## Task 1: Add the 10-tier cosmetic CSS

**Files:**
- Modify: `index.html` — insert after the existing `nm` rules at line 1888 (`.gm-name.nm-hi{color:#fff;}`).

- [ ] **Step 1: Insert the CSS ladder + keyframes**

Immediately AFTER line 1888 (`.gm-name.nm-hi{color:#fff;}`), insert:

```css
    /* level cosmetic ladder — applied to card name (.gm-name) + leaderboard name (.gm-lbrow .nm) */
    .gm-lbrow .nm.gm-lv1,.gm-name.gm-lv1{color:#8b949e;}
    .gm-lbrow .nm.gm-lv2,.gm-name.gm-lv2{color:#7ee3f5;font-weight:700;}
    .gm-lbrow .nm.gm-lv3,.gm-name.gm-lv3{color:#ffffff;font-weight:800;}
    .gm-lbrow .nm.gm-lv4,.gm-name.gm-lv4{color:#22d3ee;font-weight:800;}
    .gm-lbrow .nm.gm-lv5,.gm-name.gm-lv5,
    .gm-lbrow .nm.gm-lv6,.gm-name.gm-lv6,
    .gm-lbrow .nm.gm-lv7,.gm-name.gm-lv7,
    .gm-lbrow .nm.gm-lv8,.gm-name.gm-lv8,
    .gm-lbrow .nm.gm-lv9,.gm-name.gm-lv9,
    .gm-lbrow .nm.gm-lv10,.gm-name.gm-lv10{-webkit-background-clip:text;background-clip:text;color:transparent;font-weight:800;}
    .gm-lbrow .nm.gm-lv5,.gm-name.gm-lv5{background-image:linear-gradient(90deg,#e3b341,#f0c674);}
    .gm-lbrow .nm.gm-lv6,.gm-name.gm-lv6{background-image:linear-gradient(90deg,#e3b341,#f0c674);filter:drop-shadow(0 0 6px #e3b34177);}
    .gm-lbrow .nm.gm-lv7,.gm-name.gm-lv7{background-image:linear-gradient(90deg,#7c3aed,#22d3ee);filter:drop-shadow(0 0 6px #7c3aed88);}
    .gm-lbrow .nm.gm-lv8,.gm-name.gm-lv8{background-image:linear-gradient(90deg,#7c3aed,#22d3ee,#7c3aed);background-size:200% auto;animation:gmShimmer 3s linear infinite;}
    .gm-lbrow .nm.gm-lv9,.gm-name.gm-lv9{background-image:linear-gradient(90deg,#7c3aed,#22d3ee,#7c3aed);background-size:200% auto;animation:gmShimmer 3s linear infinite,gmAura 2s ease-in-out infinite;}
    .gm-lbrow .nm.gm-lv10,.gm-name.gm-lv10{background-image:linear-gradient(90deg,#e3b341,#ffffff,#e3b341);background-size:200% auto;animation:gmShimmer 2.5s linear infinite,gmAuraGold 2s ease-in-out infinite;}
    @keyframes gmShimmer{to{background-position:200% center;}}
    @keyframes gmAura{0%,100%{filter:drop-shadow(0 0 3px #22d3ee55);}50%{filter:drop-shadow(0 0 9px #22d3eecc);}}
    @keyframes gmAuraGold{0%,100%{filter:drop-shadow(0 0 4px #e3b34166);}50%{filter:drop-shadow(0 0 11px #e3b341dd);}}
```

Notes for the implementer:
- The badge emoji is inside the same name element. Emoji render in full color even under `background-clip:text` (already proven by the live `nm-gold`), so the badge stays visible while the name text gets the gradient — the Lv.9/10 aura naturally glows the badge too (no DOM change needed).
- The old `nm-hi`/`nm-gold` rules (lines 1886-1888) become unused after Task 3 but are harmless; leave them (minimal-change).

- [ ] **Step 2: Commit**

```
git -C "c:\Users\amire\AI\stockmolt-wt-cosmetic" add index.html
git -C "c:\Users\amire\AI\stockmolt-wt-cosmetic" commit -m "feat(game): add 10-tier cosmetic name ladder CSS"
```

---

## Task 2: Add the `gmNameClass` helper

**Files:**
- Modify: `index.html` — add the helper next to `gmLevelInfo` (near line 6205-6212, inside the game IIFE).

- [ ] **Step 1: Add the helper function**

Immediately AFTER the `gmLevelInfo` function (it ends with the `return {...}` block around line 6212), insert:

```js
    // maps a level (1-10) to its cosmetic ladder class; used by card + leaderboard
    function gmNameClass(level){
      const l = Math.max(1, Math.min(10, Number(level) || 1));
      return 'gm-lv' + l;
    }
```

- [ ] **Step 2: Commit**

```
git -C "c:\Users\amire\AI\stockmolt-wt-cosmetic" add index.html
git -C "c:\Users\amire\AI\stockmolt-wt-cosmetic" commit -m "feat(game): add gmNameClass(level) helper"
```

---

## Task 3: Wire the helper into card + leaderboard

**Files:**
- Modify: `index.html:6275` (character card name) and `index.html:6558` (leaderboard row name).

- [ ] **Step 1: Replace the card name class expression**

At line 6275, replace:
```js
          +'<div class="gm-name '+(li.lvl>=5?'nm-gold':(li.lvl>=3?'nm-hi':''))+'">'+li.badge+' '+(p.display_name||'Trader')+'</div>'
```
with:
```js
          +'<div class="gm-name '+gmNameClass(li.lvl)+'">'+li.badge+' '+(p.display_name||'Trader')+'</div>'
```

- [ ] **Step 2: Replace the leaderboard row name class**

At line 6558, replace:
```js
          var nmCls=(x.level>=5)?'nm-gold':((x.level>=3)?'nm-hi':'');
```
with:
```js
          var nmCls=gmNameClass(x.level);
```

- [ ] **Step 3: Sanity check the wiring (read-only)**

Confirm line 6558's `nmCls` is still consumed by the row HTML just below it (`<span class="nm '+nmCls+'">`). No other change needed.

- [ ] **Step 4: Commit**

```
git -C "c:\Users\amire\AI\stockmolt-wt-cosmetic" add index.html
git -C "c:\Users\amire\AI\stockmolt-wt-cosmetic" commit -m "feat(game): use gmNameClass on card + leaderboard names"
```

---

## Task 4: Update roadmap unlock labels

**Files:**
- Modify: `index.html:5923` (`GM_UNLOCKS`).

- [ ] **Step 1: Replace the GM_UNLOCKS array**

At line 5923, replace:
```js
    const GM_UNLOCKS = ['','','Name highlight on leaderboard','','Colored nickname','','','','','Hall of Fame'];
```
with:
```js
    const GM_UNLOCKS = ['','Colored name','Name highlight on leaderboard','Bright name','Gold name','Golden glow','Gradient name','Shimmer effect','Aura + badge glow','Hall of Fame'];
```

- [ ] **Step 2: Commit**

```
git -C "c:\Users\amire\AI\stockmolt-wt-cosmetic" add index.html
git -C "c:\Users\amire\AI\stockmolt-wt-cosmetic" commit -m "feat(game): roadmap labels for the cosmetic ladder"
```

---

## Task 5: Browser smoke test (manual)

There is no automated frontend test. Verify visually.

- [ ] **Step 1: Open the worktree file in a browser**

Open `c:\Users\amire\AI\stockmolt-wt-cosmetic\index.html` in Chrome, go to the game/Play view. Confirm: no red console errors; your own character-card name renders with its tier style; the leaderboard names render styled per level.

- [ ] **Step 2: Preview all 10 tiers at once (console snippet)**

The live data won't have a player at every level, so inject a temporary preview. Paste into the browser console:
```js
(()=>{const d=document.createElement('div');d.id='ladderqa';d.style.cssText='position:fixed;bottom:8px;left:8px;z-index:99999;background:#0d1117;border:1px solid #30363d;border-radius:10px;padding:10px;display:flex;flex-direction:column;gap:4px;font-size:14px;';for(let l=1;l<=10;l++){const s=document.createElement('div');s.className='gm-name gm-lv'+l;s.textContent='⚔️ Trader-Sample · Lv.'+l;d.appendChild(s);}document.body.appendChild(d);})();
```
Expected: a panel showing Lv.1→10, each visibly more elaborate (gray → cyan → white → cyan-bold → gold → gold-glow → gradient → shimmer(animated) → shimmer+aura → gold Legend). Lv.8-10 animate. Remove with: `document.getElementById('ladderqa').remove()`.

- [ ] **Step 3: Check the roadmap labels**

Open the level roadmap (the `gm-roadmap-list`) and confirm each level shows its new "🎁 ..." label (Colored name, Bright name, Golden glow, Gradient name, Shimmer effect, Aura + badge glow) instead of "🏅 New badge".

- [ ] **Step 4: Report the smoke-test result**

State explicitly what was observed (tiers render, animations run, no console errors, roadmap labels correct). If anything looks off (e.g., emoji clipped invisible, a tier indistinguishable from its neighbor), report it rather than proceeding.

---

## Go-live (after smoke test passes + 지크님 approval)

- [ ] **Step 1: Merge to main (no push yet)**

```
git -C c:\Users\amire\AI\stockmolt merge --ff-only feat/cosmetic-ladder
```

- [ ] **Step 2: Push (triggers Cloudflare Pages deploy) — REQUIRES 지크님 approval**

```
git -C c:\Users\amire\AI\stockmolt push origin main
```

- [ ] **Step 3: Verify live**

Poll `https://stockmolt.pages.dev/` until the deployed HTML contains `function gmNameClass`. Then load the live game view and confirm names render styled.

- [ ] **Step 4: Cleanup**

```
git -C c:\Users\amire\AI\stockmolt worktree remove --force "c:\Users\amire\AI\stockmolt-wt-cosmetic"
git -C c:\Users\amire\AI\stockmolt branch -d feat/cosmetic-ladder
```

---

## Self-Review notes

- **Spec coverage:** ladder (Lv1-10) → Task 1 CSS + Task 2/3 wiring. Roadmap labels → Task 4. Dual application (card + leaderboard) → Task 3 both sites. Animations Lv8+ → Task 1 (only lv8/9/10 have `animation`). Out-of-scope frames/backend → not present. ✓
- **Placeholder scan:** none — all CSS/JS is concrete. ✓
- **Type/name consistency:** `gmNameClass` defined in Task 2, used identically in Task 3 (card + leaderboard). Class names `gm-lv1..gm-lv10` match between Task 1 CSS and the helper's `'gm-lv'+l` output. ✓
- **Lv.3/Lv.5 continuity:** `gm-lv3` = white bold (= old `nm-hi`), `gm-lv5` = gold gradient (= old `nm-gold`) — existing players at these levels look the same. ✓

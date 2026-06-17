# Cosmetic Status Ladder (Phase 1c) — Design

**Date:** 2026-06-17
**Status:** Design approved, pending spec review → implementation plan
**Parent:** `2026-06-17-progression-engagement-economy-design.md` (section 1-c, deferred)

## Problem

Mid levels grant only a badge. `GM_UNLOCKS` in `index.html` is empty for Lv.2, 4, 6,
7, 8, 9 — so after the early climb there is no *felt* reward for leveling, even though
the XP grind continues. This is the progression-depth gap identified in the parent spec.

## Goal

Fill every gap level with a visible cosmetic upgrade, so each level-up changes how the
player looks **to other players** (status signal = engagement), using one coherent
escalating system rather than six unrelated effects.

## Current implementation (the pattern we extend)

Cosmetics already exist as a single level-gated nickname style applied in **two places**:

- Character card name — `index.html:6275`:
  `'<div class="gm-name '+(li.lvl>=5?'nm-gold':(li.lvl>=3?'nm-hi':''))+'">'`
- Leaderboard row name — `index.html:6558`:
  `var nmCls=(x.level>=5)?'nm-gold':((x.level>=3)?'nm-hi':'');`
- CSS — `index.html:1886-1888` (`nm-hi` = white bold, `nm-gold` = gold gradient via
  `background-clip:text`).

So the system is already dual (own card + leaderboard) and social. We extend it from a
binary (3/5) scheme to a per-level ladder.

## Approach (chosen: unified escalating ladder)

A single helper `gmNameClass(level)` returns a per-level class `gm-lv<N>`, applied to
BOTH the card name and every leaderboard row name (replacing the two inline ternaries).
The name text + badge escalate one tier per level.

### The ladder

Dark-UI palette: gold `#e3b341`, violet `#7c3aed`, cyan `#22d3ee`.

| Lv | Badge | Name treatment | Note |
|---|---|---|---|
| 1 | 🐣 | muted gray (`#8b949e`) | base |
| 2 | 🔍 | soft cyan (`#7ee3f5`) | new — first color |
| 3 | 📡 | white bold | existing `nm-hi`, preserved |
| 4 | 🎯 | bright cyan bold (`#22d3ee`) | new |
| 5 | ⚔️ | gold gradient | existing `nm-gold`, preserved |
| 6 | 🌊 | gold gradient + soft glow (`text-shadow`) | new |
| 7 | 🎲 | violet→cyan gradient + glow | new |
| 8 | 🦅 | gradient + animated shimmer (moving highlight) | new — animation starts here |
| 9 | 🛡️ | gradient + shimmer + pulsing aura + badge glow | new |
| 10 | 👑 | "Legend": gold↔white shimmer + strong aura | enhanced |

Progression: color → bold → gradient → glow → shimmer → aura → Legend. Every gap level
(2, 4, 6, 7, 8, 9) gains a distinct, visible upgrade.

**Animations (shimmer/pulse) only at Lv.8+** (approved). Founding season has few
high-level players, so leaderboard visual noise / perf cost is negligible. The shimmer
reuses the gradient `background-clip:text` technique already proven by `nm-gold`.

### Roadmap labels

Update `GM_UNLOCKS` (`index.html:5923`) so the level roadmap preview is truthful:

| Lv | Old | New label |
|---|---|---|
| 2 | '' | 'Colored name' |
| 3 | 'Name highlight on leaderboard' | (unchanged) |
| 4 | '' | 'Bright name' |
| 5 | 'Colored nickname' | 'Gold name' |
| 6 | '' | 'Golden glow' |
| 7 | '' | 'Gradient name' |
| 8 | '' | 'Shimmer effect' |
| 9 | '' | 'Aura + badge glow' |
| 10 | 'Hall of Fame' | (unchanged) |

## Scope

- **Pure frontend / CSS.** No backend, no DB, no edge-function change.
- Files touched: `index.html` only — CSS block near 1886, `gmRenderCharacter` name (6275),
  leaderboard row name (6558), `GM_UNLOCKS` (5923), and a new `gmNameClass()` helper.
- The badge glow at Lv.9/10 styles the badge emoji span; no new DOM structure.

## Out of scope (explicit)

- Separate card/leaderboard-row frames (the parent spec's "profile frame" idea) — the
  top-tier glow/aura conveys status without new framing DOM. YAGNI.
- Any backend / `season_xp` / prestige work — that is Phase 2.
- Changing level thresholds or XP (shipped in Phase 1).

## Risks & mitigations

- **Gradient text-clip browser support** — already in production via `nm-gold`; reuse the
  same technique, so no new compatibility risk.
- **Animation perf on the leaderboard** — gated to Lv.8+ and CSS-only (`background-position`
  / `opacity` keyframes), few rows affected. Acceptable.
- **Visual consistency** — card and leaderboard MUST use the same `gmNameClass(level)` so a
  player looks identical in both places (the existing pattern; preserve it).
- **Class migration** — replacing the `nm-hi`/`nm-gold` ternaries with `gmNameClass()` must
  keep Lv.3 and Lv.5 looking the same as today (map them to the preserved styles).

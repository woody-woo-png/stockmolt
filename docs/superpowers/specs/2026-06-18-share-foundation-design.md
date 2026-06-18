# Share Foundation (A) — Design

**Date:** 2026-06-18
**Status:** Design approved → implementation

## Problem

stockmolt's real bottleneck is acquisition. Two foundations are broken/missing so any channel
effort is invisible or off-brand:
1. **Meta/OG is still the old content-site identity** ("Real-time AI Market Sentiment Engine … AI
   agents debate stocks, vote on predictions"). SNS share crawlers (Twitter/FB) don't run JS, so
   the JS `_updateMeta` doesn't help — they read the static initial meta and show a non-game
   preview.
2. **No GA events and no share utm.** GA was just revived (`G-SB329EHGZV`), but share clicks,
   sign-ups, and pick submissions aren't tracked, and share links carry no utm — so "does sharing
   bring anyone in" is unmeasurable.

## Goal

Lay the share/acquisition foundation: static meta reads as the game, key funnel actions emit GA
events, and shared links are attributable. Code-only, `index.html`, no DB/backend change.

## Scope (locked)

Three parts:

### 1. Static meta → game identity
Replace the static initial-HTML meta with game copy:
- **title:** `StockMolt — Beat the AI at Daily Stock Picks`
- **description:** `Pick 3 stocks, go long or short, and duel an AI rival every market day. Beat the bot, climb the Win-vs-AI leaderboard. A free daily stock-prediction game.`
- Apply identical copy to `<title>`, `meta[name=description]`, `og:title`, `og:description`,
  `twitter:title`, `twitter:description`.
- Keep `og:url`, `og:site_name`, `og:image`, `twitter:card` (og:image replaced later in B).
- Update the home/game entries in the JS `_updateMeta` map to game copy too (client + some
  crawlers).

### 2. GA custom events
A reusable helper that no-ops when gtag is absent:
```js
function gmTrack(name, params){ try{ if(typeof gtag==='function') gtag('event', name, params||{}); }catch(e){} }
```
Emit at three points:
- **`share`** — in the share helpers (gmShareResult / gmShareTrader / gmShare), params
  `{ method: 'native'|'twitter', kind: 'result'|'trader' }`.
- **`sign_up`** — when a name is set (account created).
- **`submit_picks`** — on successful pick submission.

### 3. Share URL utm
Shared links go from `https://stockmolt.ai/` to
`https://stockmolt.ai/?utm_source=share&utm_medium={native|twitter}&utm_campaign=beat_ai`
so GA Traffic-acquisition separates share-driven visits from direct.

## Out of scope
- og:image redesign / dynamic scoreboard image (that's B).
- Any DB/backend/XP change. Acquisition channels themselves (TikTok/X/PH) — owner-driven.

## Rollout / verification
- All in `index.html` (main → Cloudflare).
- Meta: after deploy, `curl` the og tags / Twitter Card validator shows game copy.
- Events: GA Realtime/DebugView shows `share`, `sign_up`, `submit_picks` firing.
- utm: share → open → GA Traffic acquisition shows `source=share`.

## Related
[[project_measurement_and_acquisition]] · [[project_rival_reveal]]

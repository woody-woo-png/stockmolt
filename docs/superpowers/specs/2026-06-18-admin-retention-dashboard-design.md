# Admin Retention Dashboard — Design

**Date:** 2026-06-18
**Status:** Design approved, pending spec review → implementation plan

## Problem

The game is live with a tiny founding base (single-digit players, +1 overnight). The owner
needs to see whether the loop retains people — the "acquisition + retention measurement"
that is the real next mountain. There is no admin view today; player data lives in tables
reachable only by service-role edge functions.

## Goal

A lightweight, **auth-gated, read-only** retention dashboard the owner checks daily. It
answers: are new users arriving, are they coming back, and who is each one. Built on the
existing stack with **no new database objects and no new scheduled jobs**.

## Key decisions (locked)

1. **Auth = a single admin token**, not user accounts. The dashboard page prompts for a
   password once, stores it in `localStorage`, and sends it on every request; the function
   compares it to an `ADMIN_TOKEN` Supabase secret.
2. **No SQL RPC / no migration.** The `admin-stats` edge function already runs as service-role
   (bypasses RLS). It **fetches the raw rows and aggregates in TypeScript** — the data is tiny
   (`game_daily_result` is one row per player per resolved day; `players` is a handful). The
   only RPC reused is the existing `get_season_leaderboard` for the season snapshot. This keeps
   it to **one function + one static page, zero DB gates.**
3. **Counts, not rates, at single-digit N.** Percentage retention (D1/D7) with a denominator of
   2–3 is misleading. Report **raw cohort counts** + a **per-user 14-day activity grid** to
   eyeball. Switch to computed rates later when N justifies it. Using *distinct active days per
   user* sidesteps the weekend/holiday "next trading day" problem entirely.

## Architecture

- **`admin.html`** — a static shell served from the same Cloudflare Pages site (e.g.
  `stockmolt.pages.dev/admin.html`). Contains **no data**: just a password prompt + JS that
  calls the endpoint with the token and renders the result. A public URL is safe because every
  byte of data requires the token.
- **`admin-stats` edge function** (Deno, service-role) — on branch `feat/game-mvp-backend`:
  1. Read the `x-admin-token` request header; if it ≠ env `ADMIN_TOKEN`, return **401** (do not
     touch the DB).
  2. Fetch `players` (all) and `game_daily_result` (all, or last ~30 days), call
     `get_season_leaderboard` for the current season.
  3. Aggregate in TypeScript and return one JSON blob.
- **Secret:** `ADMIN_TOKEN` set via `supabase secrets set ADMIN_TOKEN=...` (owner-supplied,
  never in the repo or the page bundle).
- **CORS:** the function's `Access-Control-Allow-Headers` must include `x-admin-token`
  (the existing list does not) or the browser preflight fails.

## Metrics (v1 — counts first)

Computed in the function from `players` + `game_daily_result` (+ season RPC):

- **Totals:** total players · named players (display_name not the auto `Trader-xxxxxx`) ·
  active today (distinct players with a `game_daily_result` for today, or `last_played_date` =
  today) · players with a live streak (`streak_current > 0`).
- **Last 14 days, per day:** `new_players` (count of `players.created_at` on that date) and
  `active_players` (distinct `game_daily_result.player_id` for that `trade_date`). Rendered as
  two small CSS-bar rows (no chart library).
- **Cohort counts (raw, not %):** returning = players with **≥2 distinct active days**;
  one-and-done = exactly 1 active day; active in last 7 days. Show "N of M".
- **Streak distribution:** buckets (0 / 1–2 / 3–6 / 7–13 / 14+) counts.
- **Per-user table:** display_name · created · last active · distinct active days ·
  streak_current/best · level · capital · rounds (count of `game_daily_result`) · beat-AI rate
  (share of rounds with `beat_ai = true`).
- **14-day activity grid:** one row per player, 14 cells (●=active that day, ·=not) — the
  primary at-this-scale signal (eyeball who's coming back).
- **Season snapshot:** current season name + top `season_xp` rows from `get_season_leaderboard`.

## Data sources (existing columns, verified)

- `players`: `id, device_id, display_name, level, xp, streak_current, streak_best, capital,
  last_played_date, claimed, created_at`. (`created_at` + `last_played_date` confirmed present
  in `004_game_tables.sql`.)
- `game_daily_result`: `player_id, trade_date, xp_earned, beat_ai, correct_count,
  capital_before, capital_after`.
- `get_season_leaderboard(start, end, limit)` — existing RPC (Phase 2a).

## Rollout

No DB migration. Gates:
1. **Set the `ADMIN_TOKEN` secret** + **deploy `admin-stats`** (owner approval; the secret is
   owner-supplied). Smoke: a request with the right token returns JSON; a wrong/missing token
   returns 401.
2. **Push `admin.html`** via `main` → Cloudflare (owner approval). Verify: open
   `/admin.html`, enter the password, see the dashboard; clear the token → blank/locked.

## Out of scope (explicit)

- Computed D1/D7 retention rates (counts now; rates when N grows).
- Per-user actions / editing / impersonation — this is **read-only**.
- Charts beyond simple CSS bars; any BI tool (Metabase/Grafana) — overkill now.
- Infra/uptime monitoring — this is a product-retention view, not ops.
- Multiple admin accounts / roles — one shared token.

## Risks & mitigations

- **Data exposure** → all data requires the `ADMIN_TOKEN`; the page ships no data and the
  function returns 401 without it. Token lives only in the owner's browser `localStorage` and
  the function secret. Never commit it.
- **Token in localStorage** → acceptable for a single owner on their own device; rotate by
  changing the secret (invalidates the stored token).
- **Aggregation cost** → trivial at this scale; if `game_daily_result` grows large later, cap
  the fetch to the last 30 days (enough for the 14-day views) — noted for future.
- **CORS preflight** → `x-admin-token` added to allow-headers (see Architecture).

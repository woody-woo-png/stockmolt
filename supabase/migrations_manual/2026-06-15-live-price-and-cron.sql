-- Same-day live loop (Phase 1/A) — run in SQL Editor at DEPLOY time (Task 9), AFTER A1 verification.
-- MORNING variant: generate pre-open (10:30 UTC), resolve post-close same-day (20:30 UTC),
-- live-price cron every 2 min during the session (13:30-20:00 UTC, EDT).
-- trade_date = today (unchanged) -> streak-safe, no trading-calendar math.

------------------------------------------------------------------------
-- 1) live-price cache columns (idempotent)
------------------------------------------------------------------------
alter table game_ticker_pool add column if not exists live_price numeric;
alter table game_ticker_pool add column if not exists live_price_at timestamptz;

------------------------------------------------------------------------
-- 2) Reschedule crons.
--    ⚠️ STEP A — RUN THIS FIRST and read the output to confirm the REAL jobnames/ids.
--    The generate + resolve jobs were created manually; names below are the expected
--    defaults but MUST be verified. If a jobname differs, edit the two alter_job calls.
------------------------------------------------------------------------
select jobid, jobname, schedule, active, command from cron.job order by jobid;

--    STEP B — reschedule generate -> pre-open 10:30 UTC (weekdays),
--             resolve -> post-close 20:30 UTC (weekdays, same-day settle).
--    Adjust jobname strings if STEP A showed different names.
select cron.alter_job((select jobid from cron.job where jobname = 'game-pool-daily'),   schedule => '30 10 * * 1-5');
select cron.alter_job((select jobid from cron.job where jobname = 'game-resolve-daily'), schedule => '30 20 * * 1-5');

------------------------------------------------------------------------
-- 3) NEW cron: refresh live prices every 2 min during the regular session.
--    cron.schedule upserts by name, so re-running is safe (no duplicate).
------------------------------------------------------------------------
select cron.schedule('game-live-prices', '*/2 13-20 * * 1-5',
  $$ select net.http_post(
       url := 'https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1/update-live-prices',
       headers := '{"Content-Type":"application/json","apikey":"sb_publishable_8-tR6LbXU-l0qdgFmYnH-A_WxSuuBi0","Authorization":"Bearer sb_publishable_8-tR6LbXU-l0qdgFmYnH-A_WxSuuBi0"}'::jsonb) $$);

------------------------------------------------------------------------
-- 4) Verify final schedules — THIS IS A HARD GATE, DO NOT SKIM.
--    Expected output:
--      game-pool-daily     30 10 * * 1-5
--      game-resolve-daily  30 20 * * 1-5
--      game-live-prices    */2 13-20 * * 1-5
--    ⚠️ FAILURE MODE: if a jobname was wrong, alter_job no-ops silently and
--    generate keeps firing at 21:30 UTC. A pool born at 21:30 is already PAST
--    the 20:00 close -> the frontend reads phase='settled' -> NEVER pickable
--    -> the whole game silently breaks. If the rows below do NOT show the
--    three schedules above, STOP and fix the jobnames before walking away.
------------------------------------------------------------------------
select jobname, schedule, active
from cron.job
where jobname in ('game-pool-daily', 'game-resolve-daily', 'game-live-prices')
order by jobname;

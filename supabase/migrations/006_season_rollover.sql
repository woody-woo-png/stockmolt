-- supabase/migrations/006_season_rollover.sql
-- Phase 2b: season finalize + finish awards (rollover rides daily game-resolve; no new cron).

ALTER TABLE game_seasons ADD COLUMN IF NOT EXISTS finalized boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS game_season_award (
  season_no   int  NOT NULL REFERENCES game_seasons(season_no),
  player_id   uuid NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  rank        int  NOT NULL,
  tier        text NOT NULL,          -- 'champion' | 'finalist'
  awarded_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (season_no, player_id)
);
ALTER TABLE game_season_award ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION get_season_standings(p_start date, p_end date)
RETURNS TABLE(player_id uuid, season_xp bigint, rank int)
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  WITH sums AS (
    SELECT l.player_id, COALESCE(SUM(l.xp_delta),0)::bigint AS sx
    FROM game_xp_ledger l
    WHERE l.trade_date BETWEEN p_start AND p_end
    GROUP BY l.player_id
    HAVING SUM(l.xp_delta) > 0
  )
  SELECT s.player_id, s.sx AS season_xp,
         (RANK() OVER (ORDER BY s.sx DESC))::int AS rank
  FROM sums s
  ORDER BY rank;
$$;
REVOKE EXECUTE ON FUNCTION get_season_standings(date,date) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION get_season_standings(date,date) TO service_role;

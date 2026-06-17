-- supabase/migrations/005_seasons.sql
-- Phase 2a: seasons + prestige. Season XP is DERIVED from game_xp_ledger (no players change, no cron).

-- 1) seasons config
CREATE TABLE IF NOT EXISTS game_seasons (
  season_no   int  PRIMARY KEY,
  name        text NOT NULL,
  start_date  date NOT NULL,
  end_date    date NOT NULL     -- inclusive
);

INSERT INTO game_seasons (season_no, name, start_date, end_date)
VALUES (1, 'Season 1', '2026-06-17', '2026-08-16')
ON CONFLICT (season_no) DO NOTHING;

-- 2) prestige badges (one row = permanent "S{n} Legend")
CREATE TABLE IF NOT EXISTS game_prestige (
  player_id   uuid NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  season_no   int  NOT NULL REFERENCES game_seasons(season_no),
  awarded_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (player_id, season_no)
);

-- 3) index so the season-window aggregation stays cheap
CREATE INDEX IF NOT EXISTS idx_xp_ledger_trade_date ON game_xp_ledger(trade_date);

-- 4) RLS: edge-function (service-role) only; no anon policy
ALTER TABLE game_seasons  ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_prestige ENABLE ROW LEVEL SECURITY;

-- 5) RPC: season leaderboard (top N by ledger sum in the window)
CREATE OR REPLACE FUNCTION get_season_leaderboard(p_start date, p_end date, p_limit int)
RETURNS TABLE(display_name text, level int, season_xp bigint)
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  SELECT p.display_name, p.level, COALESCE(SUM(l.xp_delta),0)::bigint AS season_xp
  FROM game_xp_ledger l JOIN players p ON p.id = l.player_id
  WHERE l.trade_date BETWEEN p_start AND p_end
  GROUP BY p.id, p.display_name, p.level
  HAVING SUM(l.xp_delta) > 0
  ORDER BY season_xp DESC
  LIMIT p_limit;
$$;

-- 6) RPC: a viewer's own season xp + rank (pin-my-rank)
CREATE OR REPLACE FUNCTION get_season_my_rank(p_start date, p_end date, p_device text)
RETURNS TABLE(display_name text, season_xp bigint, rank int)
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  WITH sums AS (
    SELECT p.id, p.display_name, p.device_id, COALESCE(SUM(l.xp_delta),0)::bigint AS sx
    FROM players p JOIN game_xp_ledger l ON l.player_id = p.id
    WHERE l.trade_date BETWEEN p_start AND p_end
    GROUP BY p.id, p.display_name, p.device_id
  )
  SELECT s.display_name, s.sx AS season_xp,
         ((SELECT COUNT(*) FROM sums s2 WHERE s2.sx > s.sx)::int + 1) AS rank
  FROM sums s
  WHERE s.device_id = p_device AND s.sx > 0;
$$;

-- 7) only edge functions (service-role) may call the RPCs
REVOKE EXECUTE ON FUNCTION get_season_leaderboard(date,date,int) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION get_season_my_rank(date,date,text)    FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION get_season_leaderboard(date,date,int) TO service_role;
GRANT  EXECUTE ON FUNCTION get_season_my_rank(date,date,text)    TO service_role;

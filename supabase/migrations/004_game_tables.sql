-- supabase/migrations/004_game_tables.sql
-- StockMolt Trader RPG (게임 MVP) 테이블.
-- 쓰기/판정은 service-role Edge Function 전용. anon은 비민감 테이블만 read.

-- 1) players: 익명 device-id 기반 플레이어
CREATE TABLE IF NOT EXISTS players (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id        text NOT NULL UNIQUE,
  email            text,
  display_name     text,
  level            int  NOT NULL DEFAULT 1,
  xp               int  NOT NULL DEFAULT 0,
  streak_current   int  NOT NULL DEFAULT 0,
  streak_best      int  NOT NULL DEFAULT 0,
  capital          numeric NOT NULL DEFAULT 100000,
  last_played_date date,
  claimed          boolean NOT NULL DEFAULT false,
  created_at       timestamptz NOT NULL DEFAULT now()
);

-- 2) game_ticker_pool: 그날 제공 종목 + 진입/청산 시세(감사용)
CREATE TABLE IF NOT EXISTS game_ticker_pool (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trade_date     date NOT NULL,
  ticker         text NOT NULL,
  market         text NOT NULL DEFAULT 'US',
  sector         text,
  entry_price    numeric,
  exit_price     numeric,
  entry_price_at timestamptz,
  exit_price_at  timestamptz,
  price_source   text,
  resolved       boolean NOT NULL DEFAULT false,
  UNIQUE (trade_date, ticker)
);

-- 3) game_daily_rival: 그날의 고정 라이벌 AI(제출 전 확정)
CREATE TABLE IF NOT EXISTS game_daily_rival (
  trade_date date PRIMARY KEY,
  agent_id   uuid NOT NULL REFERENCES agents(id) ON DELETE RESTRICT
);

-- 4) game_pick: 사용자 픽 (하루 정확히 3개)
CREATE TABLE IF NOT EXISTS game_pick (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id   uuid NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  trade_date  date NOT NULL,
  ticker      text NOT NULL,
  direction   text NOT NULL CHECK (direction IN ('long','short')),
  created_at  timestamptz NOT NULL DEFAULT now(),
  resolved    boolean NOT NULL DEFAULT false,
  return_pct  numeric,
  correct     boolean,
  UNIQUE (player_id, trade_date, ticker)
);

-- 5) game_ai_pick: 라이벌 AI 콜 (6종목 전체)
CREATE TABLE IF NOT EXISTS game_ai_pick (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id    uuid NOT NULL REFERENCES agents(id) ON DELETE RESTRICT,
  trade_date  date NOT NULL,
  ticker      text NOT NULL,
  direction   text NOT NULL CHECK (direction IN ('long','short')),
  return_pct  numeric,
  correct     boolean,
  UNIQUE (agent_id, trade_date, ticker)
);

-- 6) game_daily_result: 플레이어 일일 집계 (결과화면/리더보드/XP 정합성)
CREATE TABLE IF NOT EXISTS game_daily_result (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id        uuid NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  trade_date       date NOT NULL,
  picks_count      int  NOT NULL,
  avg_return_pct   numeric NOT NULL,
  correct_count    int  NOT NULL,
  win_rate_daily   numeric NOT NULL,
  capital_before   numeric NOT NULL,
  capital_after    numeric NOT NULL,
  xp_earned        int  NOT NULL,
  beat_ai          boolean NOT NULL,
  ai_agent_id      uuid,
  ai_avg_return_pct numeric,
  resolved_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (player_id, trade_date)
);

-- 7) game_xp_ledger: XP 원장 (append-only, 중복지급 방지)
CREATE TABLE IF NOT EXISTS game_xp_ledger (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id   uuid NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  trade_date  date,
  reason      text NOT NULL,
  xp_delta    int  NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (player_id, trade_date, reason)
);

CREATE INDEX IF NOT EXISTS idx_game_pick_player_date ON game_pick(player_id, trade_date);
CREATE INDEX IF NOT EXISTS idx_game_pick_unresolved ON game_pick(trade_date) WHERE resolved = false;
CREATE INDEX IF NOT EXISTS idx_game_ai_pick_date ON game_ai_pick(trade_date);
CREATE INDEX IF NOT EXISTS idx_game_pool_unresolved ON game_ticker_pool(trade_date) WHERE resolved = false;
CREATE INDEX IF NOT EXISTS idx_players_capital ON players(capital DESC);
CREATE INDEX IF NOT EXISTS idx_players_xp ON players(xp DESC);

-- RLS
ALTER TABLE players            ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_ticker_pool   ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_daily_rival   ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_pick          ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_ai_pick       ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_daily_result  ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_xp_ledger     ENABLE ROW LEVEL SECURITY;

-- 비민감 테이블만 anon read 허용 (프론트 직접 조회용). 쓰기 정책 없음 = service-role 전용.
CREATE POLICY "pool_anon_read"   ON game_ticker_pool FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "rival_anon_read"  ON game_daily_rival FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "aipick_anon_read" ON game_ai_pick     FOR SELECT TO anon, authenticated USING (true);
-- players / game_pick / game_daily_result / game_xp_ledger: anon 정책 없음 → Edge Function(service-role)으로만 접근.

-- supabase/migrations/004_weekend_quiz.sql
-- weekend_coins: 주말 퀴즈 플레이로 획득한 코인 누적값
-- last_weekend_quiz_date: 같은 날 중복 제출 방지용 날짜

ALTER TABLE players
  ADD COLUMN IF NOT EXISTS weekend_coins          int  NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS last_weekend_quiz_date date;

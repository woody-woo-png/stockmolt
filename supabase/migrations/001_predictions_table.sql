-- supabase/migrations/001_predictions_table.sql
CREATE TABLE IF NOT EXISTS predictions (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  post_id             uuid NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  agent_id            uuid NOT NULL REFERENCES agents(id) ON DELETE RESTRICT,
  ticker              text NOT NULL,
  direction           text NOT NULL CHECK (direction IN ('bullish', 'bearish')),
  confidence          text NOT NULL DEFAULT 'medium'
                          CHECK (confidence IN ('high', 'medium', 'low')),
  entry_price         numeric NOT NULL,
  threshold_pct       numeric NOT NULL DEFAULT 3.0,
  verify_after        timestamptz NOT NULL,
  horizon_days        int NOT NULL DEFAULT 3,
  outcome             text DEFAULT NULL
                          CHECK (outcome IN ('correct', 'incorrect', 'inconclusive')),
  outcome_price       numeric,
  outcome_checked_at  timestamptz,
  created_at          timestamptz DEFAULT now(),
  CONSTRAINT outcome_consistency CHECK (
    outcome IS NULL
    OR (outcome_price IS NOT NULL AND outcome_checked_at IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_predictions_agent_id
  ON predictions(agent_id);

CREATE INDEX IF NOT EXISTS idx_predictions_verify
  ON predictions(verify_after, outcome)
  WHERE outcome IS NULL;

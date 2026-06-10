-- supabase/migrations/002_predictions_rls.sql
-- RLS for predictions table:
--   - anon/authenticated: read-only (leaderboard Trust Score, Trust Record Modal)
--   - insert/update/delete: service role only (Edge Functions use service key)

ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "predictions_anon_read"
  ON predictions
  FOR SELECT
  TO anon, authenticated
  USING (true);

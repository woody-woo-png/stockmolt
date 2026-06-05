-- supabase/migrations/003_prediction_amendments.sql
ALTER TABLE predictions
  ADD COLUMN amended_at              timestamptz DEFAULT NULL,
  ADD COLUMN original_prediction_id  uuid        DEFAULT NULL
    REFERENCES predictions(id);

CREATE INDEX idx_predictions_original
  ON predictions(original_prediction_id)
  WHERE original_prediction_id IS NOT NULL;

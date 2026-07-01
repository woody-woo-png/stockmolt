-- Human posts support
-- Run in Supabase Dashboard > SQL Editor

ALTER TABLE posts ADD COLUMN IF NOT EXISTS human_author TEXT;

-- Sentinel agent for all human posts (fixed UUID)
INSERT INTO agents (id, name, persona, game_roster, game_external)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  'Human',
  'Community member',
  false,
  false
) ON CONFLICT (id) DO NOTHING;

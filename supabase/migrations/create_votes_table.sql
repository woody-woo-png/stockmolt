-- votes 테이블: 외부 봇 투표 중복 방지용
-- Supabase 대시보드 > SQL Editor 에서 실행하세요.

-- 기존 테이블이 있으면 제거 후 재생성
DROP TABLE IF EXISTS votes CASCADE;

CREATE TABLE votes (
  id         uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
  agent_id   uuid        NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  post_id    uuid        NOT NULL REFERENCES posts(id)  ON DELETE CASCADE,
  vote_side  text        NOT NULL CHECK (vote_side IN ('bull', 'bear')),
  created_at timestamptz DEFAULT now()
);

-- 동일 agent가 동일 post에 1번만 투표 가능
CREATE UNIQUE INDEX votes_agent_post_unique ON votes(agent_id, post_id);

-- RLS: anon은 읽기 전용, service role은 모두 허용
ALTER TABLE votes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read votes"
  ON votes FOR SELECT
  USING (true);

CREATE POLICY "Service role can insert votes"
  ON votes FOR INSERT
  WITH CHECK (true);

-- A1 agent standings — run in Supabase SQL Editor
-- agents: game standings columns
alter table agents add column if not exists game_capital numeric not null default 100000;
alter table agents add column if not exists game_updated_at timestamptz;
alter table agents add column if not exists game_roster boolean not null default false;

-- agents' daily 3 picks (mirrors game_pick)
create table if not exists game_agent_pick (
  id uuid primary key default gen_random_uuid(),
  agent_id uuid not null references agents(id) on delete cascade,
  trade_date date not null,
  ticker text not null,
  direction text not null check (direction in ('long','short')),
  return_pct numeric,
  correct boolean,
  resolved boolean not null default false,
  created_at timestamptz not null default now(),
  unique (agent_id, trade_date, ticker)
);
create index if not exists idx_game_agent_pick_date on game_agent_pick(trade_date);

-- once-per-day compounding guard + history (mirrors game_daily_result)
create table if not exists game_agent_result (
  id uuid primary key default gen_random_uuid(),
  agent_id uuid not null references agents(id) on delete cascade,
  trade_date date not null,
  avg_return_pct numeric not null,
  correct_count int not null,
  capital_before numeric not null,
  capital_after numeric not null,
  created_at timestamptz not null default now(),
  unique (agent_id, trade_date)
);

-- server-only (service_role bypasses RLS; anon denied)
alter table game_agent_pick enable row level security;
alter table game_agent_result enable row level security;

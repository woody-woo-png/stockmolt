-- A1 roster selection — run in Supabase SQL Editor AFTER the standings schema
-- 1) Preview candidates (지크 can choose specific names instead):
select id, name, persona, created_at from agents order by created_at asc limit 30;

-- 2) Default roster = first 12 agents by created_at. Adjust the WHERE to hand-pick by name if preferred.
update agents set game_roster = true
where id in (select id from agents order by created_at asc limit 12);

-- 3) Verify
select count(*) as roster_count from agents where game_roster;
select name, persona, game_capital from agents where game_roster order by name;

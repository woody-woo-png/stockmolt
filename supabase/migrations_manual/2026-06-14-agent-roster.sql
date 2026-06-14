-- A1 roster selection — run in Supabase SQL Editor AFTER the standings schema
-- Curated 12: distinct trading personas + good display names. Excludes the duplicated
-- "ziq-Trader" rows (collide with the human player handle "Ziq") and the bland
-- "...new AI agent learning" personas (Rich-LLM-*, Gamma-LLM-*), which produce undifferentiated picks.

-- 0) (optional) reset any prior roster flag so re-runs are clean
update agents set game_roster = false where game_roster;

-- 1) Mark the curated roster
update agents set game_roster = true
where name in (
  'BullBot-EN','BearBot-EN','BullBot-KR','BearBot-KR',
  'Tech-Optimist','Reality-Check','Data-Miner','Crypto-King',
  'Dividend-Dad','YOLO-Trader','Macro-Guru','Chart-Wizard'
);

-- 2) Verify — roster_count should be 12 (if higher, a name above is duplicated; dedupe before relying on it)
select count(*) as roster_count from agents where game_roster;
select name, persona, game_capital from agents where game_roster order by name;

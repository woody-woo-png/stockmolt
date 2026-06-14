-- Vision B MVP — external (self-submitting) agents flag. Run in Supabase SQL Editor.
alter table agents add column if not exists game_external boolean not null default false;

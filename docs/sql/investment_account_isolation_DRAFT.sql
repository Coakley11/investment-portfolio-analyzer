-- DRAFT. NOT APPROVED. DO NOT RUN until the owner approves each phase.
-- Kept outside supabase/migrations on purpose so no tool applies it.
-- Database-level account isolation for the suite tables the Investment app uses.
-- The Supabase project is shared by every suite app (Command Center, Music, Baseball,
-- NBA, Future Lens, Applied Intelligence), so each phase affects all of them.
--
-- Before any phase: run docs/sql/investment_account_isolation_preflight.sql (read-only),
-- export B1/B2 as CSV, and confirm the project's backup / PITR window covers today.
-- No statement below changes, moves or deletes an existing row.
--
-- Why this is needed even with RLS on: the apps call PostgREST with the service-role key,
-- which bypasses RLS. RLS (already on for all six tables, with no policies, since the
-- 2026-10-30 containment) stops the public anon key. For the apps' own traffic the
-- database must refuse cross-account writes itself; these triggers and keys do that
-- for every app at once, whatever its code does.

------------------------------------------------------------------------------
-- Phase 1: no account can take over another account's row, and no ownerless writes.
-- Works on today's primary key (app). A colliding upsert fails with 42501 instead of
-- silently replacing the row and its user_id.
------------------------------------------------------------------------------
create or replace function public.suite_keep_row_owner()
returns trigger
language plpgsql
as $$
begin
  if tg_op = 'UPDATE' and new.user_id is distinct from old.user_id then
    raise exception '% row belongs to another account', tg_table_name
      using errcode = '42501';
  end if;
  if new.user_id is null then
    raise exception '% write has no account (user_id is null)', tg_table_name
      using errcode = '42501';
  end if;
  return new;
end
$$;

create trigger suite_app_current_state_keep_owner
before insert or update on public.suite_app_current_state
for each row execute function public.suite_keep_row_owner();

create trigger suite_resume_items_keep_owner
before insert or update on public.suite_resume_items
for each row execute function public.suite_keep_row_owner();

create trigger suite_activity_events_keep_owner
before insert or update on public.suite_activity_events
for each row execute function public.suite_keep_row_owner();

create trigger suite_saved_items_keep_owner
before update on public.suite_saved_items
for each row execute function public.suite_keep_row_owner();

create trigger suite_user_settings_keep_owner
before update on public.suite_user_settings
for each row execute function public.suite_keep_row_owner();

-- NOTE on the insert half (user_id is null refused): a sign-in-less install with no
-- suite_user_id would start failing. Preflight P6 shows whether any such writer exists
-- recently; if one does, drop "insert or" from the first three triggers.

-- Phase 1 rollback:
-- drop trigger if exists suite_app_current_state_keep_owner on public.suite_app_current_state;
-- drop trigger if exists suite_resume_items_keep_owner on public.suite_resume_items;
-- drop trigger if exists suite_activity_events_keep_owner on public.suite_activity_events;
-- drop trigger if exists suite_saved_items_keep_owner on public.suite_saved_items;
-- drop trigger if exists suite_user_settings_keep_owner on public.suite_user_settings;
-- drop function if exists public.suite_keep_row_owner();

------------------------------------------------------------------------------
-- Phase 2: one state row per (account, app). Cannot fail while app is the key.
-- Run on its own (CONCURRENTLY cannot run inside a transaction).
------------------------------------------------------------------------------
create unique index concurrently if not exists suite_app_current_state_user_app_key
  on public.suite_app_current_state (user_id, app);

-- Phase 2 rollback:
-- drop index concurrently if exists public.suite_app_current_state_user_app_key;

------------------------------------------------------------------------------
-- Phase 3: profile bindings are append-only (one Supabase Auth user per profile).
-- The fixed app stores them as suite_user_settings rows with app = '_auth_binding'.
------------------------------------------------------------------------------
create or replace function public.suite_auth_binding_immutable()
returns trigger
language plpgsql
as $$
begin
  if old.app = '_auth_binding'
     and (new.settings ->> 'auth_user_id') is distinct from (old.settings ->> 'auth_user_id') then
    raise exception 'profile binding cannot be reassigned' using errcode = '42501';
  end if;
  return new;
end
$$;

create trigger suite_user_settings_binding_immutable
before update on public.suite_user_settings
for each row execute function public.suite_auth_binding_immutable();

-- Phase 3 rollback:
-- drop trigger if exists suite_user_settings_binding_immutable on public.suite_user_settings;
-- drop function if exists public.suite_auth_binding_immutable();

------------------------------------------------------------------------------
-- Phase 4: the primary key becomes (user_id, app). Only when preflight P6 shows 0
-- ownerless state rows, after Phases 1-2, and after this app's fix is deployed.
-- Afterwards two accounts can each hold e.g. 'investment__guest' (their own sandbox)
-- instead of the second one being refused.
------------------------------------------------------------------------------
begin;
lock table public.suite_app_current_state in share row exclusive mode;
do $$
begin
  if exists (select 1 from public.suite_app_current_state where user_id is null) then
    raise exception 'ownerless rows present: stop and decide per row';
  end if;
end
$$;
alter table public.suite_app_current_state alter column user_id set not null;
alter table public.suite_app_current_state drop constraint suite_app_current_state_pkey;
alter table public.suite_app_current_state
  add constraint suite_app_current_state_pkey primary key using index suite_app_current_state_user_app_key;
commit;

-- Phase 4 rollback (only while no app key is held by two accounts):
-- select app from public.suite_app_current_state group by app having count(*) > 1;  -- must be empty
-- begin;
-- alter table public.suite_app_current_state drop constraint suite_app_current_state_pkey;
-- alter table public.suite_app_current_state add primary key (app);
-- create unique index if not exists suite_app_current_state_user_app_key
--   on public.suite_app_current_state (user_id, app);
-- commit;

------------------------------------------------------------------------------
-- Later (not drafted here): per-user JWT requests with RLS policies on auth.uid().
-- Needs an auth_user_id column on suite_users (the '_auth_binding' rows give its
-- values) and every suite app sending the signed-in user's token instead of the
-- service-role key.
------------------------------------------------------------------------------

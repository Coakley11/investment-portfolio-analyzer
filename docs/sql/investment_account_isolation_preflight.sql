-- READ-ONLY. Investment Portfolio Analyzer: where each account's data is stored today.
-- Every statement is a SELECT. Nothing is written, moved or deleted.
-- Run in the Supabase SQL editor one block at a time, and keep the results with the
-- backup (block B1) before deploying fix/account-isolation-20261119.
-- See docs/INVESTMENT_ACCOUNT_ISOLATION.md for how to read each block.

------------------------------------------------------------------------------
-- P1. Profiles. Each signed-in account resolves to exactly one external_id:
--     daniel.cohen11 -> 'daniel', coakley11 -> 'coakley11', anyone else -> their own.
--     Rows whose external_id is an email address were created by the old sign-in code
--     (ensure_user_row(external_id=<email>)) and hold no portfolio data of their own.
------------------------------------------------------------------------------
select u.external_id,
       left(u.id::text, 8)                                   as user_id_prefix,
       u.created_at,
       (select count(*) from public.suite_app_current_state s where s.user_id = u.id) as state_rows,
       (select s.settings ->> 'auth_user_id' is not null
          from public.suite_user_settings s
         where s.user_id = u.id and s.app = '_auth_binding')  as bound_to_auth_user
  from public.suite_users u
 order by u.created_at;

------------------------------------------------------------------------------
-- P2. Every Investment state row: who owns it, and what portfolio it holds.
--     Key 'investment' is workspace daniel; 'investment__<ws>' is workspace <ws>.
------------------------------------------------------------------------------
select s.app,
       u.external_id                                                     as owner,
       s.updated_at,
       s.summary,
       s.metrics -> 'full_session' ->> 'holdings_fingerprint'             as holdings_fp,
       jsonb_array_length(coalesce(s.metrics -> 'full_session' -> 'portfolio_transactions', '[]'::jsonb))
                                                                         as txn_count,
       s.metrics -> 'full_session' -> 'real_portfolio_ledger' ->> 'updated_at' as ledger_updated_at
  from public.suite_app_current_state s
  left join public.suite_users u on u.id = s.user_id
 where s.app = 'investment' or s.app like 'investment\_\_%'
 order by s.app;

------------------------------------------------------------------------------
-- P3. Key / owner mismatch: a workspace key owned by a different profile.
--     'investment' should be owned by daniel; 'investment__coakley11' by coakley11.
--     Demo keys (__ariel, __guest, __test_user) owned by daniel are the allowed case.
------------------------------------------------------------------------------
select s.app,
       u.external_id as owner,
       case when s.app = 'investment' then 'daniel'
            else substr(s.app, length('investment__') + 1) end as key_workspace,
       s.updated_at
  from public.suite_app_current_state s
  left join public.suite_users u on u.id = s.user_id
 where (s.app = 'investment' or s.app like 'investment\_\_%')
   and coalesce(u.external_id, '(no owner)') <>
       case when s.app = 'investment' then 'daniel'
            else substr(s.app, length('investment__') + 1) end
   and substr(s.app, length('investment__') + 1) not in ('ariel', 'guest', 'test_user');

------------------------------------------------------------------------------
-- P4. Who wrote under each Investment key (events + resume items keep their own
--     user_id, so they preserve history the single state row lost). Lower bound only.
------------------------------------------------------------------------------
select w.app, coalesce(u.external_id, '(no user)') as writer, w.source,
       count(*) as writes, min(w.at) as first_write, max(w.at) as last_write
  from (
        select app, user_id, 'event' as source, "timestamp"::timestamptz as at
          from public.suite_activity_events
         where app = 'investment' or app like 'investment\_\_%'
        union all
        select app, user_id, 'resume' as source, updated_at as at
          from public.suite_resume_items
         where app = 'investment' or app like 'investment\_\_%'
       ) w
  left join public.suite_users u on u.id = w.user_id
 group by w.app, u.external_id, w.source
 order by w.app, last_write desc;

------------------------------------------------------------------------------
-- P5. The real (Fidelity) transactions in every Investment row, one line each.
--     Use this to find the $1 deposit / VTI purchase and decide which account it
--     belongs to. Ticker, action, date and amounts only.
------------------------------------------------------------------------------
select s.app,
       u.external_id as owner,
       t ->> 'date'            as txn_date,
       t ->> 'action'          as action,
       t ->> 'ticker'          as ticker,
       t ->> 'quantity'        as quantity,
       t ->> 'execution_price' as execution_price,
       t ->> 'id'              as txn_id
  from public.suite_app_current_state s
  left join public.suite_users u on u.id = s.user_id
 cross join lateral jsonb_array_elements(
         coalesce(s.metrics -> 'full_session' -> 'portfolio_transactions', '[]'::jsonb)) t
 where s.app = 'investment' or s.app like 'investment\_\_%'
 order by s.app, txn_date;

------------------------------------------------------------------------------
-- P6. Ownerless Investment rows (written with no user_id). The fixed app never shows
--     these to any account and never claims them; each needs an owner decision.
------------------------------------------------------------------------------
select 'suite_app_current_state' as tbl, count(*) from public.suite_app_current_state
 where (app = 'investment' or app like 'investment\_\_%') and user_id is null
union all
select 'suite_activity_events', count(*) from public.suite_activity_events
 where (app = 'investment' or app like 'investment\_\_%') and user_id is null
union all
select 'suite_resume_items', count(*) from public.suite_resume_items
 where (app = 'investment' or app like 'investment\_\_%') and user_id is null;

------------------------------------------------------------------------------
-- P7. Database protection actually in place (expected after 2026-10-30 Step 1:
--     RLS on for all six tables, anon/authenticated without privileges).
------------------------------------------------------------------------------
select c.relname,
       c.relrowsecurity                                   as rls_enabled,
       has_table_privilege('anon', c.oid, 'SELECT')        as anon_select,
       has_table_privilege('anon', c.oid, 'UPDATE')        as anon_update,
       has_table_privilege('authenticated', c.oid, 'SELECT') as authenticated_select,
       (select count(*) from pg_policies p where p.schemaname = 'public' and p.tablename = c.relname) as policies,
       (select string_agg(t.tgname, ', ') from pg_trigger t where t.tgrelid = c.oid and not t.tgisinternal) as triggers
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace and n.nspname = 'public'
 where c.relname in ('suite_users', 'suite_app_current_state', 'suite_activity_events',
                     'suite_resume_items', 'suite_saved_items', 'suite_user_settings')
 order by c.relname;

------------------------------------------------------------------------------
-- B1. BACKUP (read-only export). Run, then "Download CSV" in the SQL editor, and keep
--     the file. One row per Investment state row, the full JSON included, so any row
--     can be restored exactly as it is today.
------------------------------------------------------------------------------
select now() as exported_at, s.app, s.user_id, u.external_id as owner, s.updated_at,
       s.page, s.summary, s.metrics::text as metrics_json
  from public.suite_app_current_state s
  left join public.suite_users u on u.id = s.user_id
 where s.app = 'investment' or s.app like 'investment\_\_%'
 order by s.app;

-- B2. BACKUP of the per-account settings rows (goals / preferences), same procedure.
select now() as exported_at, s.user_id, u.external_id as owner, s.app, s.updated_at,
       s.settings::text as settings_json
  from public.suite_user_settings s
  left join public.suite_users u on u.id = s.user_id
 order by u.external_id, s.app;

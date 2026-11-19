# Investment Portfolio Analyzer: account isolation

Branch `fix/account-isolation-20261119`. Status: code fixed and tested; **not deployed**; no database change has been run.

## Symptom

`coakley11` and `daniel.cohen11` saw the same portfolio and the same real (Fidelity) transactions. A change in one account appeared in the other.

## Root cause

Four defects combined. Each alone could mix accounts.

| # | Where | Defect | Effect |
|---|---|---|---|
| 1 | `suite_workspace_registry.py`, `suite_workspace.py` | Ownership checks accepted only `dict` sessions. Streamlit's `st.session_state` is a `SessionStateProxy` (a `MutableMapping`, not a `dict`), so in the deployed app `get_owned_workspace_id()` always returned `""`, and `normalize_workspace_id("")` is `daniel`. | Every signed-in account was clamped onto workspace `daniel`, the private workspace of daniel.cohen11. Unit tests passed plain dicts, so they never saw it. |
| 2 | `suite_user.py` | `_resolve_account_user_id()` was `lru_cache(maxsize=1)` with no arguments. One Python process serves every browser session. | The first account resolved after a cache reset was returned to **every** session: one user's reads and writes used another user's `user_id`. The owner's 2026-10-30 preflight shows exactly this pattern (profile and workspace key crossed between `daniel` and `coakley11`, minutes apart). |
| 3 | Supabase `suite_app_current_state` | Primary key is `app` alone; saves are plain upserts. | Two accounts writing key `investment` share **one row**; each save replaced the other account's row and its `user_id`. |
| 4 | Disk (`data/workspaces/<ws>/…`) | Disk state was keyed by workspace only. The server disk is shared by all sessions, and disk wins over cloud on restore. | With both accounts on workspace `daniel`, both read and wrote the same `investment_user_state.json`. |

Contributing defects, also fixed:

- `_infer_external_id_from_email`: any email containing `daniel` or `ariel` became that profile (`danielle@…` → `daniel`).
- `resolve_auth_external_id` fell back to `daniel`; `allowed_workspaces_for_user("")` returned the owner's workspaces.
- Admin accounts (coakley11 is one) could switch into `daniel` as a "demo preset", but `daniel` is a real account's workspace.
- Signed-out sessions fell back to the owner's `suite_user_id` from Secrets; an exception in the sign-in gate let the app continue signed-out.
- Logout left the workspace choice and the cloud `full_session` cache in the session.
- Activity / resume reads included rows with no `user_id` for every account.
- `save_current_state` checked the scoped key (`investment__coakley11`) against the plain app list, so **every cloud save outside workspace `daniel` was silently skipped** while reporting success. Accounts other than daniel had no cloud persistence: their data lived only on the server's temporary disk.

## How identity and isolation work now

1. **Identity = the Supabase Auth user of this session.** At sign-in, `resolve_account_profile_id(email, auth_user_id)` picks a profile id:
   - `profile_emails` in Secrets (exact address → profile, same format as Baseball Explorer);
   - otherwise the continuity pins `daniel.cohen11 → daniel`, `coakley11 → coakley11` (what each account already used, so their data stays where it is). A `profile_emails` map that does not list these exact addresses does not move them;
   - otherwise the email's local part (`user_<x>` when it names a protected id such as `daniel`, `guest`).

   The profile is then **bound** to that Auth user (a `suite_user_settings` row, `app = '_auth_binding'`, first claim wins, re-read after write). If the profile is bound to a different Auth user, the account gets `<candidate>_<hash of its Auth id>`. So two Auth users never share a profile.
2. **Account id** (`suite_users.id`) is resolved per session from that profile. The cache is keyed by profile, never "the current user".
3. **Workspace** = the profile id. `daniel` is offered only to daniel.cohen11. Demo presets (`ariel`, `guest`, `test_user`) remain for admins but are per-account sandboxes.
4. **Disk**: sign-in on → `data/accounts/<profile>/workspaces/<ws>/`. No signed-in account → no disk read or write. Sign-in off (single-user laptop) → unchanged `data/workspaces/<ws>/`.
5. **Cloud**: every read filters `user_id = <this account>`. With sign-in on and no account, reads return empty and writes raise `AccountScopeError`. Before a state upsert, the app checks the row's owner and refuses to replace a row owned by another account, or an ownerless one. This is the app-side twin of DB Phase 1.
6. **Session boundary**: whenever the signed-in Auth user changes (logout, login as another account, token restore), every in-memory copy of account data is dropped: portfolio, transactions, workspace choice, cloud caches.
7. **Sign-in gate fails closed**: an error in the gate stops the page.
8. **Admin** (developer tools, demo workspaces): only the signed-in coakley11 / daniel.cohen11 accounts, and only while the session holds that account's own **bound** profile. An email's local part alone (`coakley11@any-domain`) no longer grants admin: a second Auth user with that local part gets a private profile and no admin. Optional exact allow-list: `admin_emails = ["…", "…"]` under `[suite_activity]` (or `SUITE_ADMIN_EMAILS`, comma-separated).

## Where the data is today, and what needs reconciliation

I had no access to the production database or the Streamlit Cloud disk (no secrets locally, by design). From the code and the owner's 2026-10-30 preflight:

- **Cloud row `investment`** (workspace daniel) is owned by profile `daniel`. Because of defects 1–3, it is almost certainly the **one shared portfolio both accounts were editing**. It contains whatever was saved last, from either account.
- **Cloud row `investment__coakley11`**: probably absent. Cloud saves for that key were silently skipped (see above).
- **Disk** `data/workspaces/daniel/investment_user_state.json` on the Streamlit server: the shared file, ephemeral (lost on reboot/redeploy).
- **Hypothetical portfolios and real transactions** are both inside `metrics.full_session` of those rows (`holdings_df`, `portfolio_transactions`, `real_portfolio_ledger`).

**After deployment, with no reconciliation:**
- daniel.cohen11 sees the current `investment` row (the shared portfolio, including the $1 deposit / VTI purchase if it was saved there).
- coakley11 starts empty in the cloud.

Nothing is deleted, merged or reassigned automatically.

**Ambiguity to resolve (the fix will not guess):**
- Which account the existing shared portfolio and the Fidelity VTI transaction belong to. Preflight P5 lists every transaction per row; P4 shows which profile wrote under each key and when.
- If the VTI transaction is coakley11's, it should be **copied** (not moved) to coakley11 after deploy, by re-entering it in coakley11, or by an owner-approved copy of the row to `investment__coakley11` owned by `coakley11`. Then remove it from daniel.cohen11 only if you decide to.
- Ownerless rows (P6) are hidden from every account until you decide on them.

## Backup / recovery path

1. Run `docs/sql/investment_account_isolation_preflight.sql` P1–P7 (read-only) and keep the output.
2. Run B1 and B2 and **Download CSV**. `metrics_json` / `settings_json` restore any row exactly.
3. Confirm the Supabase backup / PITR window covers the deploy date.
4. Optional: download `data/` from the Streamlit Cloud container if you still rely on the disk copy (it does not survive a redeploy anyway).

## Deployment steps (each needs your approval)

1. Backup (above).
2. Optionally set exact addresses in Secrets so continuity does not depend on the local-part pins:
   ```toml
   [suite_activity.profile_emails]
   "daniel.cohen11@<domain>" = "daniel"
   "coakley11@<domain>" = "coakley11"
   ```
   If an Ariel (or other preset) account exists, add it here **before** deploying, or it starts on a new `user_ariel` profile (old data untouched).
3. Deploy the branch to Dev first. Sign in as each account **yourself first**: the first sign-in binds `daniel` and `coakley11` to your two Auth users.
4. Run DB Phase 1 and Phase 2 (`docs/sql/investment_account_isolation_DRAFT.sql`); later Phase 3 and Phase 4.
5. Port the same identity fix to the other suite apps that share the database (Command Center, Music, NBA, Future Lens, Applied Intelligence). They still use the substring email rule and the global cache, and the Command Center reads and writes every app's key.

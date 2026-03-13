# Echo 2.0 — CRM for Aksia
## Project Overview
Echo 2.0 is a purpose-built CRM system for Aksia, an investment management and advisory firm. It replaces the current Microsoft Power Apps-based "Echo" platform. The PRD (Echo_2.0_PRD_v1.0.docx) is the source of truth for all product decisions and should be consulted for field definitions, business logic, and module specs.

## Tech Stack
- **Backend:** FastAPI (Python 3.12)
- **Templating:** Jinja2 (server-side HTML — no frontend framework)
- **Frontend interactivity:** HTMX (loaded via CDN)
- **Styling:** Tailwind CSS (loaded via CDN — no build step, no Node.js)
- **Database:** Supabase (PostgreSQL) via supabase-py
- **Authentication:** Microsoft Entra ID SSO via MSAL (Microsoft Authentication Library for Python)
- **Hosting:** Railway
- **No Node.js. No npm. No React. No Next.js. No frontend build pipeline of any kind.**

## Project Structure
```
echo2/
├── main.py                  # FastAPI app entry point
├── config.py                # Settings loaded from environment variables
├── requirements.txt
├── .env                     # Never commit this
├── .env.example
├── .gitignore
├── CLAUDE.md                # This file
├── routers/                 # One file per module
│   ├── organizations.py
│   ├── people.py
│   ├── activities.py
│   ├── leads.py
│   ├── contracts.py
│   ├── fund_prospects.py
│   ├── distribution_lists.py
│   ├── tasks.py
│   ├── dashboards.py
│   └── admin.py
├── models/                  # Pydantic models
│   ├── organization.py
│   ├── person.py
│   ├── activity.py
│   ├── lead.py
│   ├── contract.py
│   ├── fund_prospect.py
│   ├── distribution_list.py
│   ├── task.py
│   └── user.py
├── db/
│   ├── client.py            # Supabase client init
│   └── schema.sql           # Full database schema
├── templates/               # Jinja2 HTML templates
│   ├── base.html
│   ├── index.html
│   ├── organizations/
│   ├── people/
│   ├── activities/
│   ├── leads/
│   ├── fund_prospects/
│   ├── dashboards/
│   └── admin/
└── static/
    └── css/
        └── custom.css
```

## Two Business Lines — Critical Context
Aksia has two distinct but connected business lines that share the same contacts and organizations:

1. **Advisory / Discretionary / Research** — relationship-driven, institutional clients, long RFP cycles. Pipeline tracked via Leads → Contracts. Revenue metric is FLAR (Forward-Looking Accrual Revenue = base fees only, no performance fees).

2. **Products / AC Private Markets (ACPM)** — fundraising operation for commingled funds. Pipeline tracked via Fund Prospects. The four current funds are:
   - APC (Aksia Private Credit Fund) — Aksia brand
   - CAPIX (ACPM Private Credit) — ACPM brand
   - CAPVX (ACPM Private Equity) — ACPM brand
   - HEDGX (ACPM Hedge Funds) — ACPM brand
   - All funds have offshore feeder funds. Offshore custodian = Aksia. Domestic custodian = Calamos (for ACPM funds).

## User Roles & Permissions
| Role | Key Permissions |
|------|----------------|
| Admin | Full access. User management, reference data, audit log, duplicate merge, data quality alerts. |
| Legal | View all. Edit Contracts only (start date, service type, asset classes, fees). |
| RFP Team | Standard access + can edit RFP Hold field on Organizations. |
| Standard User | Create/edit Orgs, People, Activities, Leads, Fund Prospects. Cannot edit Contracts or RFP Hold. Cannot hard-delete. |
| Read Only | View and export only. No create or edit. |

- All auth via Microsoft Entra ID SSO (MSAL)
- New users auto-provisioned as Standard User on first login
- Role stored in users table, checked on every request via dependency injection

## Database Rules — Always Follow These
- Every table has: `id UUID PRIMARY KEY DEFAULT uuid_generate_v4()`, `created_at TIMESTAMPTZ DEFAULT now()`, `updated_at TIMESTAMPTZ DEFAULT now()`, `created_by UUID REFERENCES users(id)`
- All deletes are SOFT deletes: every entity table has `is_archived BOOLEAN NOT NULL DEFAULT FALSE`. Never use SQL DELETE. Filter `WHERE is_archived = FALSE` on all queries.
- Every field-level change must be written to the `audit_log` table: record_type, record_id, field_name, old_value, new_value, changed_by, changed_at
- Dropdown values are NEVER hardcoded in Python or HTML. They always come from the `reference_data` table. Query by category (e.g. `WHERE category = 'organization_type'`). All 17 categories are seeded in schema.sql.
- Row-level security is enforced in Supabase. The service role key is used server-side only — never expose it to the browser.

## Key Business Logic — Always Follow These
- **Do Not Contact:** When enabled on a Person, automatically remove them from all distribution lists (log the removal in audit_log) and suppress from all future sends.
- **RFP Hold:** When enabled on an Organization, suppress all contacts at that org from distribution list send previews.
- **L2 superset of L1:** For each asset class publication list, L2 members automatically receive L1. Enforced at data level.
- **Lead → Contract promotion:** Only triggered when Lead rating changes to "Inactive [Won Mandate – Aksia Client]". System auto-sets end_date to today and creates a Contract record inheriting service_type, asset_classes, and expected_revenue from the Lead. Contract is then editable by Legal only.
- **Coverage:** Stored at Contact level (optional) and Lead level (required). Organization page shows a read-only rollup of all contact and lead coverage — never stored at org level.
- **FLAR:** Forward-Looking Accrual Revenue. Base advisory fees only. No performance or incentive fees included. Tracked as expected_yr1_flar and expected_longterm_flar on Leads.
- **Fund Prospects:** Domestic and offshore are separate records (different share_class field). Same org can have both.
- **Next Steps Date on Lead or Fund Prospect:** Auto-generates a Task assigned to the Aksia Owner when saved.
- **Activity Follow-Up Required:** Auto-generates a Task assigned to the activity author when saved.

## Coding Standards
- Use FastAPI dependency injection for auth on every route: `current_user: User = Depends(get_current_user)`
- Check role permissions inside each router using a helper: `require_role(current_user, ["admin", "standard"])`
- All Supabase queries go through `db/client.py` — never import supabase directly in routers
- Use Pydantic models for all request/response validation
- Jinja2 templates extend `base.html` using `{% extends "base.html" %}` and `{% block content %}{% endblock %}`
- HTMX responses return partial HTML fragments (not full pages) when the request has `HX-Request` header
- Always check `request.headers.get("HX-Request")` to determine whether to return a full page or a partial
- Never put sensitive data (Supabase keys, MSAL secrets) in templates or static files

## Environment Variables (never hardcode these)
Defined in `config.py` via pydantic-settings. See `.env.example` for the full list.
```
SUPABASE_URL=
SUPABASE_KEY=
ENTRA_CLIENT_ID=
ENTRA_CLIENT_SECRET=
ENTRA_TENANT_ID=
ENTRA_REDIRECT_URI=http://localhost:8000/auth/callback
SECRET_KEY=                  # For session signing
DEBUG=true
BASE_URL=http://localhost:8000
```
**Note:** `config.py` uses a `@model_validator(mode="after")` (not `__init__`) to derive `entra_authority` from `entra_tenant_id`. This is required for pydantic-settings v2 compatibility.

## What Has Been Built So Far
- [x] Project scaffold and folder structure
- [x] requirements.txt
- [x] config.py (pydantic-settings v2 with model_validator)
- [x] db/client.py (cached Supabase singleton)
- [x] db/schema.sql (20 tables, all indexes, triggers, seed data for all reference_data categories)
- [x] main.py (mounts all 10 routers, Jinja2 templates, session middleware)
- [x] base.html (sidebar nav with grouped sections, global search, HTMX + Tailwind CDN)
- [x] Pydantic models — Create/Update/Response for all 10 entities
- [x] Router stubs — all 10 modules with TODO placeholders
- [x] Template stubs — list/detail/form for all modules, 3 dashboard views, admin views
- [x] Organizations module (router logic, templates, HTMX partials, duplicate detection)
- [x] People module (router logic, templates, HTMX org autocomplete, DNC enforcement, duplicate detection)
- [x] Activities module (router logic, templates, HTMX org/person autocomplete, follow-up task generation, fund tags)
- [x] Leads module (router logic, templates, stage-gated validation, Lead→Contract promotion, next-steps task generation)
- [x] Contracts module (router logic, templates, Legal-only edit, fee arrangements CRUD)
- [x] Fund Prospects module (router logic, templates, stage progression, next-steps task generation)
- [x] Distribution Lists module (router logic, templates, member management, send preview/history, L2 superset, DNC/RFP Hold suppression)
- [x] Tasks module (router logic, templates, My Tasks/All Tasks views, HTMX status transitions, polymorphic record linking, overdue highlighting)
- [ ] Dashboards module (router logic)
- [ ] Admin module (router logic)
- [ ] Reference Data management
- [ ] SSO / Auth
- [ ] Data migration
- [x] Dummy data seed script (`scripts/seed_data.py` — ~3,400 rows across all tables)

## Open Items (from PRD Section 15)
1. Entra ID Tenant ID and SSO app registration — IT team
2. Ostrako NDA export format — Ostrako/IT team
3. Authorized senders for publication lists — Marketing Publications
4. Declined reason codes for Fund Prospects — Product team
5. Offshore feeder fund distribution list structure — Product/IR team
6. Soft Circle vs Hard Circle logic — Product team
7. Management dashboard access list — Leadership
8. Audit log access list beyond Admins — Leadership
9. Data migration scope (Echo-era only vs Backstop-era) — Miles/Admin team
10. Events management spec — Aggeliki/Marketing
11. CRM name (Echo 2.0 or new name) — Leadership
12. General newsletter scope — Marketing Publications
13. crm.aksia.com DNS configuration — IT
14. Railway deployment configuration — Miles/IT

## Schema Design Decisions
- `reference_data` table uses composite unique on `(category, value)` with optional `parent_value` for subtypes (e.g. activity subtypes scoped to parent type)
- Person ↔ Org is a many-to-many via `person_organization_links` with `link_type` (primary/secondary/former)
- Activity ↔ Org and Activity ↔ Person are separate junction tables
- Tags are polymorphic: `record_tags` has `record_type` + `record_id` columns
- Tasks are polymorphic: `linked_record_type` + `linked_record_id`
- `pg_trgm` extension enabled for fuzzy duplicate detection on org names and person names
- Full-text search index on `activities.details` using `to_tsvector('english', details)`
- All `updated_at` columns have `BEFORE UPDATE` triggers via `update_updated_at()` function
- Distribution lists have `l2_superset_of` self-referencing FK for L2→L1 enforcement
- 4 funds seeded: APC, CAPIX, CAPVX, HEDGX

## Session Notes
_Use this section to track decisions made during Claude Code sessions:_

### Session 1 — March 11, 2026
- Decided to use is_archived (boolean) for soft deletes, not deleted_at timestamp
- Removed starlette from requirements.txt (FastAPI manages it internally)
- Fixed config.py to use model_validator(mode="after") for entra_authority
- httpx and aiofiles added to requirements.txt
- schema.sql approved and ready to apply to Supabase
- .env created locally with Supabase credentials (Entra ID still placeholder)
- Supabase was down — schema not yet applied. Next step: apply schema.sql, verify 20 tables, run uvicorn

### Session 2 — March 12, 2026
- Built full Organizations module: router (CRUD, search, filters, pagination, audit logging, duplicate detection, soft delete), 11 templates (list, detail, form, 6 tab partials, list table partial, duplicate warning partial)
- Created `dependencies.py` with `get_current_user` (dev stub returning admin user) and `require_role` helper — to be replaced with real MSAL auth later
- Added `check_org_name_similarity()` PostgreSQL function to schema.sql for fuzzy org name matching via pg_trgm
- Route ordering: `/new` and `/check-duplicates` placed before `/{org_id}` to avoid path conflicts
- RFP Hold permission enforcement: only admin and rfp_team can toggle; warning banner on detail page
- Coverage rollup: computed from linked people + leads, never stored at org level
- Client Questionnaire: conditionally visible when relationship_type = client, with disclosure toggle
- Next step: People module

### Session 3 — March 12, 2026
- Built full People module: router (CRUD, search, filters, pagination, audit logging, duplicate detection, soft delete, DNC enforcement), 8 templates (list, detail, form, 3 tab partials, list table partial, duplicate warning partial)
- Added `check_person_name_similarity()` PostgreSQL function to schema.sql for fuzzy person name matching via pg_trgm (includes primary org name in results)
- HTMX-powered org autocomplete on person form (search-orgs endpoint returns clickable dropdown)
- Primary Organization is required on person create; stored in `person_organization_links` with link_type = primary
- When primary org changes, old org automatically marked as "former" (per PRD Section 4.3)
- Do Not Contact toggle: confirmation dialog, removes from all `distribution_list_members`, each removal logged to audit_log
- Legal & Compliance Notices field hidden when DNC is enabled
- Asset Classes of Interest: multi-select checkboxes from reference_data table
- Coverage Owner defaults to record creator when not specified
- Person form can be pre-filled with org via `?org=<org_id>` query param (for "Add Person" from org detail page)
- Added `backstop_company_id` and `ostrako_id` to Pydantic model (PRD Table 7 legacy fields)
- Distribution list membership tab is read-only for now — add/remove will be built with the Distribution Lists module
- Next step: Activities module

### Session 4 — March 12, 2026
- Built full Activities module: router (CRUD, search, filters, pagination, audit logging, soft delete, follow-up task auto-generation), 4 templates (list, detail, form, list table partial)
- Activity types and subtypes loaded from `reference_data` table; subtypes dynamically fetched via HTMX when type changes (meeting has 5 subtypes)
- Multi-select HTMX autocomplete for both Linked Organizations (required, 1+) and Linked People (optional, 0+)
- Org/person links stored in `activity_organization_links` and `activity_people_links` junction tables; fully synced on create/update
- Follow-Up Required toggle: when enabled, auto-creates a Task assigned to the activity author with due date and notes
- Fund Tags: multi-select checkboxes from `funds` table, stored as UUID array in `fund_tags` column
- Activity form pre-fillable with org (`?org=<id>`) or person (`?person=<id>`) from their detail pages
- List page filters: search (title/details), type, author, date range; sortable columns; pagination
- Detail page shows linked orgs/people, fund tags, follow-up section with generated tasks
- Color-coded type badges: call=blue, meeting=purple, email=green, note=gray, conference=yellow, webinar=indigo
- Notification/email feature deferred to Phase 2 (field stored but not sent)
- Next step: Leads module

### Session 5 — March 12, 2026
- Built full Leads module: router (CRUD, search, filters, pagination, audit logging, soft delete, stage-gated validation, Lead→Contract promotion, next-steps task auto-generation), 5 templates (list, detail, form, list table partial)
- Stage-gated field validation: fields required based on lead stage (Exploratory → Radar → Focus → Verbal Mandate → Inactive). Validation enforced server-side; visibility controlled client-side via JavaScript
- Stage hierarchy: exploratory=1, radar=2, focus=3, verbal_mandate=4, won/lost=5. Each stage unlocks additional required fields
- Lead → Contract promotion: when rating changes to "won", system auto-sets end_date=today and creates a Contract record inheriting organization_id, service_type, asset_classes, expected_revenue→actual_revenue, potential_coverage→client_coverage
- Next Steps Date auto-task: when next_steps_date is set or changed, creates a Task assigned to aksia_owner_id with due_date=next_steps_date, linked_record_type="lead"
- Organization linked via HTMX single-select autocomplete (different from Activities' multi-select pattern)
- Added `risk_weight` reference_data category (high/medium/low) to schema.sql — per rule that dropdowns must never be hardcoded
- Conditional field visibility: previous_flar shown only for Extension/Re-Up relationships; pricing_proposal_details shown when proposal != no_proposal; rfp_expected_date shown when rfp_status != not_applicable; legacy_onboarding_holdings shown when legacy_onboarding=true
- Color-coded stage badges: exploratory=gray, radar=blue, focus=yellow, verbal_mandate=purple, won=green, lost=red
- Stage progress bar on detail page showing visual pipeline progression
- List page filters: search (org name + summary), stage, owner, service type, relationship, date range; sortable columns; pagination
- Currency formatting for revenue and FLAR fields using Jinja `'{:,.0f}'.format()` pattern
- Next step: Contracts module

### Session 6 — March 12, 2026
- Built full Contracts module: router (list, detail, Legal-only edit, archive, audit logging), 4 templates (list, detail, form, list table partial)
- Created Fee Arrangements CRUD: 5 endpoints on `/contracts/fee-arrangements/` for create, edit, archive (inline HTMX forms on org detail page)
- Created `models/fee_arrangement.py` with Create/Update/Response Pydantic models
- Contracts are NOT manually created — only via Lead→Contract promotion (already in leads.py)
- Legal-only edit restriction: `require_role(current_user, ["admin", "legal"])` on edit/update routes
- Organization and Originating Lead are always read-only on contracts (displayed as text, not inputs)
- Conditional field visibility: Inflation Provision and Escalator Clause hidden when service_type = "project" or "product" (JS on form, Jinja2 on detail)
- Fee arrangement end_date only visible/required when status = "inactive"
- Fee arrangements are org-level, NOT Legal-restricted — standard users can CRUD them
- Fee arrangement forms load as HTMX partials inline on the org detail page's Fee Arrangements tab
- Updated `_tab_fee_arrangements.html` with New/Edit/Archive buttons wired to HTMX endpoints
- Color-coded service type badges: advisory=blue, discretionary=purple, research=green, reporting=gray, project=yellow, product=orange
- Contract detail page includes: originating lead card with link, audit history (collapsible), permission notice for non-legal users
- Route ordering: fee arrangement routes defined BEFORE `{contract_id}` routes to avoid UUID parse conflicts
- `_audit_changes()` helper takes `record_type` parameter (used for both "contract" and "fee_arrangement")
- Next step: Fund Prospects module

### Session 7 — March 12, 2026
- Built full Fund Prospects module: router (CRUD, search, filters, pagination, audit logging, soft delete, stage validation, next-steps task auto-generation), 5 templates (list, detail, form, list table partial, org tab partial update)
- 10 fundraising stages from PRD Table 18: Target Identified → Intro Scheduled → Initial Meeting Complete → DDQ / Materials Sent → Due Diligence → IC Review → Soft Circle → Legal / Docs → Closed → Declined
- Decline Reason conditional: required and visible only when stage=Declined; loaded from `decline_reason` reference_data category (7 placeholder values)
- Stage Entry Date auto-set to today when stage changes on update (or on create)
- Next Steps Date auto-task: when set or changed, creates Task assigned to aksia_owner_id with linked_record_type="fund_prospect"
- Linked Lead dropdown: scoped to leads for the selected organization; refreshes via fetch() when org changes in the autocomplete
- HTMX endpoint `/fund-prospects/leads-for-org` returns `<option>` elements for the linked lead dropdown
- Fund ticker enrichment: on list page, all 4 funds loaded into a dict for O(1) lookups; on detail page, _get_fund_info() helper
- Color-coded stage badges: target_identified=gray, intro_scheduled=blue, initial_meeting_complete=indigo, ddq_materials_sent=cyan, due_diligence=yellow, ic_review=orange, soft_circle=purple, legal_docs=pink, closed=green, declined=red
- Share class displayed as colored badge: domestic=blue, offshore=teal
- Fund ticker displayed as monospace badge on list and detail pages
- Org detail Fund Prospects tab updated: added Fund (ticker) column, "New Fund Prospect" button pre-filled with org, enriched fund_prospects with ticker via funds_map
- Stage progress bar on detail page: 8 pipeline stages + 1 outcome slot (Closed=green, Declined=red)
- Allocation metrics displayed in highlighted grid cards: Target, Soft Circle, Hard Circle, Probability
- Permissions: view=all, create/edit=admin+standard_user+rfp_team, archive=admin only
- No promotion logic (unlike Leads→Contracts) — Closed stage is terminal
- Next step: Distribution Lists module

### Session 8 — March 12, 2026
- Built full Distribution Lists module: router (CRUD, search, filters, pagination, audit logging, member management, send preview/history, L2 superset enforcement, DNC/RFP Hold suppression), 7 templates (list, detail, form, list table partial, members tab, send history tab, send preview partial)
- 17 official publication lists from PRD Table 20 supported: Publication (HF/PE/PC/RA L1+L2), Newsletter, Fund (APC/CAPIX/CAPVX/HEDGX/ACPM Combined), plus custom/event lists
- L2-superset-of-L1 enforcement: `l2_superset_of` FK on L2 list points to L1 list. Send preview for L1 list reverse-queries L2 lists and merges their members (deduplicated). Note shown on detail page and send preview.
- DNC suppression: DNC people cannot be added to lists (blocked at search + add endpoint). DNC members excluded from send preview with separate "Excluded (DNC)" section.
- RFP Hold suppression: people at RFP Hold organizations are NOT removed from lists, but suppressed from send previews. Shown in separate "Excluded (RFP Hold)" section with org name.
- Member management: HTMX person search autocomplete on detail page; add/remove via POST endpoints. Add handles reactivation of previously soft-removed members (UNIQUE constraint on distribution_list_id + person_id).
- Member soft-removal: sets `is_active=False`, `removed_at=now()`, `removal_reason='manual'` (preserves audit trail). Note: DNC enforcement in people.py uses hard DELETE (existing behavior unchanged).
- Send workflow: Preview shows included/excluded split with counts. Confirm saves `send_history` record with JSONB `recipient_snapshot` capturing exact audience. Actual email delivery via Power Automate is Phase 2.
- Custom list privacy: non-admin users see official + own custom + public custom lists. Query uses `.or_("is_official.eq.true,owner_id.eq.{uid},is_private.eq.false")`.
- Permissions: view=all, create custom=admin+standard_user+rfp_team, edit official=admin only, edit own custom=owner, add/remove members=admin+standard_user+rfp_team, send official=admin only (authorized senders TBD), send own custom=owner, archive=admin only
- `distribution_lists` table uses `is_active` (not `is_archived`). All queries filter `.eq("is_active", True)`.
- Color-coded type badges: publication=blue, newsletter=green, fund=purple, event=yellow, custom=gray
- Brand badges: Aksia=brand color, ACPM=indigo
- Official/Custom badges: Official=green, Custom=gray
- Detail page has two tabs: Members (with inline add/remove) and Send History (with expandable detail view per send)
- Form has conditional field visibility: Brand shown for publication/newsletter/fund types; Asset Class for publication/fund; L2 Superset Of dropdown for publication type only; Private checkbox hidden when Official is checked
- L1 publication lists dropdown in form: filtered to official publication lists with no `l2_superset_of` set (i.e., they are L1)
- Route ordering: /search-people and /new placed before /{list_id} to avoid UUID parse conflicts
- Next step: Tasks module

### Session 9 — March 12, 2026
- Built full Tasks module: router (CRUD, search, filters, pagination, audit logging, soft delete, HTMX quick status transitions, polymorphic record linking), 4 templates (list, detail, form, list table partial)
- Two views: "My Tasks" (personal, default landing via sidebar) and "All Tasks" (full list with all filters)
- Sidebar link updated from `/tasks` to `/tasks/my-tasks` so clicking "Tasks" goes to user's personal task view
- HTMX inline status transitions: "Start" button (open→in_progress), "Complete" button (in_progress→complete) — returns HTML fragment targeting `#task-status-{id}` for seamless in-place update
- Status badges: open=yellow, in_progress=blue, complete=green, cancelled=gray
- Source badges: manual=gray, activity_follow_up=blue, lead_next_steps=purple, fund_prospect_next_steps=indigo
- Overdue highlighting: `bg-red-50` row background, `text-red-600 font-semibold` due date, "(overdue)" suffix, red "OVERDUE" badge on detail page. Overdue = `due_date < today AND status in (open, in_progress)`
- Overdue-only filter implemented at DB level: `.lt("due_date", today).in_("status", ["open", "in_progress"])`
- Batch resolution for linked records and user names on list page to avoid N+1 queries: `_batch_resolve_linked_records()` groups by type, does one `.in_()` query per type; `_batch_resolve_users()` for assignee names
- Single-record `_resolve_linked_record()` for detail page: supports activity→title, lead→org name+summary, fund_prospect→org name+ticker, organization→company_name, person→full name
- Polymorphic record search on form: HTMX endpoint `/tasks/search-records` searches by type (organization/person/lead/fund_prospect), record type selector + search input, selected record shown as chip
- Record search for leads/fund_prospects: searches organizations first, then finds linked leads/fund_prospects via org_id
- Form pre-fill support: `?linked_type=lead&linked_id=<uuid>` pre-populates the linked record chip (for "Add Task" from other module detail pages)
- System-generated tasks show read-only info banner: "This task was auto-generated by the system (Activity Follow-Up / Lead Next Steps / Fund Prospect Next Steps)"
- System-generated task source field is preserved on update (cannot be changed to "manual")
- Permissions: view=all, create manual=admin+standard_user+rfp_team, edit own=admin+standard_user+rfp_team+legal (assigned_to must match), edit any=admin, quick status=assignee or admin, archive=admin only
- Detail page: header card with status/overdue/source badges and quick status buttons, info grid (due date, assigned to, created, updated), notes card, linked record card with type icon + link, collapsible audit history
- All tasks sorted by `due_date ASC NULLS LAST` by default (overdue first, then soonest due)
- Route ordering: /search-records, /my-tasks, /new placed before /{task_id} to avoid UUID parse conflicts
- No model or schema changes needed — `models/task.py` and the `tasks` table were already complete
- Auto-task generation (activities/leads/fund_prospects) was already implemented in previous sessions — this module provides the CRUD layer to view and manage those tasks
- Next step: Dashboards module

### Session 10 — March 12, 2026
- Built dummy data seed script: `scripts/seed_data.py` using Faker + supabase-py
- Added `Faker==33.0.0` to requirements.txt
- Created `scripts/__init__.py` and `scripts/seed_data.py`
- Script is idempotent: checks for existing seed users (`*@aksia.test`), supports `--force` to re-seed
- Fixed random seed (42) for reproducibility
- Seeded 8 users (admin, legal, rfp_team, 4 standard, read_only) + dev user
- Seeded ~3,400 rows: 200 orgs, 500 people, 619 person-org links, 500 activities, 750+563 activity links, 200 leads, 24 contracts (from won leads), 150 fund prospects, 24 distribution lists (14 official + 10 custom), 507 list members, 198 tasks, 50 fee arrangements
- Fixed config.py: added `"extra": "ignore"` to model_config to allow extra .env vars (e.g. `database_url`)
- Fixed None-safe string slicing in task title generation for leads and fund prospects
- L2→L1 superset relationships set on publication distribution lists
- Distribution list members skip DNC people
- Tasks include overdue items (past due_date + open/in_progress status) for testing overdue highlighting
- Run: `cd echo2 && python -m scripts.seed_data` (or `--force` to re-seed)
- Server tested locally: `python -m uvicorn main:app --reload --port 8000`
- Created `feedback.md` at project root for tracking testing feedback
- Next step: Address feedback from testing, then Dashboards module

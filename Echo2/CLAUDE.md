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
├── main.py                  # FastAPI app entry point (11 routers mounted)
├── config.py                # Settings loaded from environment variables
├── dependencies.py          # Auth: CurrentUser (multi-role), get_current_user, require_role
├── requirements.txt
├── .env                     # Never commit this
├── .env.example
├── .gitignore
├── CLAUDE.md                # This file
├── routers/                 # One file per module
│   ├── organizations.py
│   ├── people.py
│   ├── activities.py
│   ├── leads.py             # Handles advisory + fundraise + product lead types
│   ├── contracts.py
│   ├── distribution_lists.py
│   ├── tasks.py
│   ├── dashboards.py        # 4 dashboards: Personal, Advisory Pipeline, Capital Raise, Management
│   ├── admin.py             # Fields, layouts, roles, users, reference data, duplicates
│   ├── documents.py
│   ├── views.py             # Saved views CRUD (save/delete/set-default)
│   └── fund_prospects.py    # LEGACY BACKUP — NOT mounted in main.py, do not use
├── models/                  # Pydantic models
│   ├── organization.py
│   ├── person.py
│   ├── activity.py
│   ├── lead.py
│   ├── contract.py
│   ├── fee_arrangement.py
│   ├── distribution_list.py
│   ├── task.py
│   └── user.py
├── services/
│   ├── form_service.py      # Dynamic form build/parse/validate/save
│   └── grid_service.py      # Reusable grid: query, enrich, paginate, saved views
├── db/
│   ├── client.py            # Supabase client init
│   ├── schema.sql           # Full database schema (30+ tables)
│   ├── migrate_schema.sql   # Migration script for Phases 1–5 (idempotent, run in Supabase SQL Editor)
│   ├── field_service.py     # EAV field definitions + custom values
│   └── helpers.py           # Shared DB helpers (audit, reference_data, batch resolve)
├── scripts/
│   ├── seed_data.py         # Dummy data seed (~3,400 rows). Run: python -m scripts.seed_data [--force]
│   ├── seed_field_definitions.py  # Seeds field_definitions for all 6 entities
│   └── migrate_fund_prospects.py  # One-time migration: fund_prospects → leads (lead_type='fundraise')
├── templates/               # Jinja2 HTML templates
│   ├── base.html
│   ├── index.html           # Personal dashboard with 7 HTMX lazy-load widgets
│   ├── components/
│   │   ├── _grid.html           # Reusable grid (table, pagination, badges, actions)
│   │   ├── _column_selector.html # Column show/hide dropdown (Alpine.js)
│   │   ├── _field_renderer.html  # Dynamic field rendering macro (12 field types)
│   │   └── _form_section.html    # Section card macro with grid layout
│   ├── organizations/
│   ├── people/
│   ├── activities/
│   ├── leads/
│   ├── contracts/
│   ├── dashboards/          # 4 full pages + 7 widget partials + 2 content partials
│   └── admin/               # fields, field_form, layout_designer, roles, role_form,
│                            # users, reference_data, duplicates + HTMX partials
└── static/
    └── css/
        └── custom.css
```

## Two Business Lines — Critical Context
Aksia has two distinct but connected business lines that share the same contacts and organizations:

1. **Advisory / Discretionary / Research** — relationship-driven, institutional clients, long RFP cycles. Pipeline tracked via Leads → Contracts. Revenue metric is FLAR (Forward-Looking Accrual Revenue = base fees only, no performance fees).

2. **Products / AC Private Markets (ACPM)** — fundraising operation for commingled funds. Pipeline tracked via Leads with `lead_type='fundraise'` or `lead_type='product'` (merged from former Fund Prospects module). The four current funds are:
   - APC (Aksia Private Credit Fund) — Aksia brand
   - CAPIX (ACPM Private Credit) — ACPM brand
   - CAPVX (ACPM Private Equity) — ACPM brand
   - HEDGX (ACPM Hedge Funds) — ACPM brand
   - All funds have offshore feeder funds. Offshore custodian = Aksia. Domestic custodian = Calamos (for ACPM funds).

## User Roles & Permissions
| Role | Key Permissions |
|------|----------------|
| Admin | Full access. User management, reference data, audit log, duplicate merge, data quality alerts. |
| Legal | View all. Create and edit Contracts only. |
| RFP Team | Standard access + can edit RFP Hold field on Organizations. |
| BD | Business Development — standard access plus lead ownership. |
| Standard User | Create/edit Orgs, People, Activities, Leads. Cannot edit Contracts or RFP Hold. Cannot hard-delete. |
| Read Only | View and export only. No create or edit. |

- All auth via Microsoft Entra ID SSO (MSAL) — currently using dev stub user until SSO is wired up
- New users auto-provisioned as Standard User on first login
- **Multi-role system:** Users can have multiple roles via `user_roles` junction table. Permissions are additive across roles. JSONB `permissions` column on `roles` table defines per-entity action grants.
- `CurrentUser` in `dependencies.py` has `roles: list[str]` (plural), with backward-compatible `role` property returning the primary role
- `require_role()` checks `if not any(r in allowed_roles for r in user.roles)`
- 6 system roles seeded in `roles` table (cannot be deleted/renamed). Custom roles can be created via admin panel.

## Database Rules — Always Follow These
- Every table has: `id UUID PRIMARY KEY DEFAULT uuid_generate_v4()`, `created_at TIMESTAMPTZ DEFAULT now()`, `updated_at TIMESTAMPTZ DEFAULT now()`, `created_by UUID REFERENCES users(id)`
- All deletes are SOFT deletes: every entity table has `is_deleted BOOLEAN NOT NULL DEFAULT FALSE` (renamed from `is_archived` in Phase 5). Never use SQL DELETE. Filter `WHERE is_deleted = FALSE` on all queries.
- Every field-level change must be written to the `audit_log` table: record_type, record_id, field_name, old_value, new_value, changed_by, changed_at
- Dropdown values are NEVER hardcoded in Python or HTML. They always come from the `reference_data` table. Query by category (e.g. `WHERE category = 'organization_type'`). All 17 categories are seeded in schema.sql.
- Row-level security is enforced in Supabase. The service role key is used server-side only — never expose it to the browser.

## Key Business Logic — Always Follow These
- **Do Not Contact:** When enabled on a Person, automatically remove them from all distribution lists (log the removal in audit_log) and suppress from all future sends.
- **RFP Hold:** When enabled on an Organization, suppress all contacts at that org from distribution list send previews.
- **L2 superset of L1:** For each asset class publication list, L2 members automatically receive L1. Enforced at data level.
- **Lead → Contract creation:** Manual, not automatic. When a Lead reaches "Won" stage, a "Create Contract" button appears on the Lead detail page (visible to Legal/Admin only). The contract creation form pre-fills from the Lead's fields. Auto-promotion was removed in Phase 5.
- **Coverage:** Stored at Contact level (optional) and Lead level (required). Organization page shows a read-only rollup of all contact and lead coverage — never stored at org level.
- **FLAR:** Forward-Looking Accrual Revenue. Base advisory fees only. No performance or incentive fees included. Tracked as expected_yr1_flar and expected_longterm_flar on Leads.
- **Fundraise Leads:** Formerly "Fund Prospects" — now merged into Leads with `lead_type='fundraise'`. Domestic and offshore are separate records (different share_class field). Same org can have both. Fund_prospects table kept as backup but no longer actively used.
- **Lead Types:** `lead_type` column discriminates: 'advisory' (default, existing pipeline), 'fundraise' (capital raise), 'product'. Stages are scoped by lead_type via `parent_value` on `lead_stage` reference_data.
- **Next Steps Date on Lead:** Auto-generates a Task assigned to the Aksia Owner when saved.
- **Activity Follow-Up Required:** Auto-generates a Task. Assignee can be selected via dropdown (defaults to activity author; suggests coverage owners at linked orgs). Follow-up notes are required when follow-up is enabled.

## Coding Standards
- Use FastAPI dependency injection for auth on every route: `current_user: CurrentUser = Depends(get_current_user)`
- Check role permissions inside each router using a helper: `require_role(current_user, ["admin", "standard"])`
- All Supabase queries go through `db/client.py` — never import supabase directly in routers
- Use shared helpers from `db/helpers.py` — never duplicate `audit_changes`, `get_reference_data`, `batch_resolve_users`, etc. in routers
- Use `services/form_service.py` for form build/parse/validate — do not hardcode form field lists in routers
- Use `services/grid_service.py` + `build_grid_context()` for all entity list pages — do not write custom list query logic
- Jinja2 templates extend `base.html` using `{% extends "base.html" %}` and `{% block content %}{% endblock %}`
- HTMX responses return partial HTML fragments (not full pages) when the request has `HX-Request` header
- Always check `request.headers.get("HX-Request")` to determine whether to return a full page or a partial
- Never put sensitive data (Supabase keys, MSAL secrets) in templates or static files
- Route ordering matters: static paths (`/new`, `/my-tasks`, `/search-*`) must be defined BEFORE `/{id}` to avoid UUID parse conflicts

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
- [x] db/schema.sql (20+ tables, all indexes, triggers, seed data for all reference_data categories, field_definitions + entity_custom_values + lead_owners + documents tables)
- [x] main.py (mounts all 10 routers, Jinja2 templates, session middleware)
- [x] base.html (sidebar nav with grouped sections, global search, HTMX + Tailwind CDN)
- [x] Pydantic models — Create/Update/Response for all 10 entities
- [x] Router stubs — all 10 modules with TODO placeholders
- [x] Template stubs — list/detail/form for all modules, 3 dashboard views, admin views
- [x] Organizations module (router logic, templates, HTMX partials, duplicate detection)
- [x] People module (router logic, templates, HTMX org autocomplete, DNC enforcement, duplicate detection)
- [x] Activities module (router logic, templates, HTMX org/person autocomplete, follow-up task generation, fund tags)
- [x] Leads module (router logic, templates, stage-gated validation, Lead→Contract promotion, next-steps task generation, lead_type support for advisory/fundraise/product)
- [x] Contracts module (router logic, templates, Legal-only edit, fee arrangements CRUD)
- [x] Distribution Lists module (router logic, templates, member management, send preview/history, L2 superset, DNC/RFP Hold suppression)
- [x] Tasks module (router logic, templates, My Tasks/All Tasks views, HTMX status transitions, polymorphic record linking, overdue highlighting)
- [x] Dashboards module (router logic, 4 dashboards: Personal/Advisory Pipeline/Capital Raise/Management, HTMX lazy-load widgets, CSS-only visualizations, HTMX filters)
- [x] Admin module — Phase 3 complete (field management CRUD, dynamic form rendering for all 6 entities, page layout designer, role management, user management)
- [x] Dynamic form system (`services/form_service.py`, `components/_field_renderer.html`, `components/_form_section.html`)
- [x] Reusable grid component (Phase 4 — `services/grid_service.py`, `components/_grid.html`, `components/_column_selector.html`, `routers/views.py`; deployed on all 7 entities)
- [x] Reference Data management (Phase 5 — admin CRUD for all 16 categories, hierarchical data support, HTMX partials)
- [x] Duplicate detection enhancements (Phase 5 — suppression pairs, "Not a Duplicate" buttons, admin batch scan page)
- [x] Soft delete rename (`is_archived` → `is_deleted` globally, admin restore endpoint)
- [x] Lead→Contract manual creation (removed auto-promotion, added contract creation form)
- [x] Distribution list bulk add, people DL membership tab, follow-up task assignee dropdown
- [x] Lead Finder virtual columns (active_leads_count on org grid, HTMX expandable panel)
- [ ] SSO / Auth (Microsoft Entra ID — awaiting IT team app registration)
- [ ] Data migration (scope TBD — awaiting Miles/Admin team)
- [x] Dummy data seed script (`scripts/seed_data.py` — ~3,400 rows across all tables)
- [x] "My X" views — My Organizations, My People, My Activities, My Fund Prospects (sidebar defaults to "My" views)
- [x] Personal dashboard coverage widgets — My Coverage, Missing Info Alerts, Stale Contacts (90+ day inactivity)
- [x] Patrick Implementation Plan — ALL 15 architectural changes complete across Phases 0–5:
  - Phase 0: Shared utilities extraction (`db/helpers.py`)
  - Phase 1: Schema foundation (field_definitions, roles/user_roles, documents, lead_owners, person-org date tracking)
  - Phase 2: Fund Prospects merged into Leads (`lead_type` discriminator, migration script)
  - Phase 3: Admin Control Panel (field management, dynamic forms for all 6 entities, page layouts, role/user management)
  - Phase 4: Reusable Grid Component (grid_service.py, _grid.html, saved views, deployed on all 7 entities)
  - Phase 5: Reference Data CRUD, Lead Finder, manual contract creation, DL improvements, soft delete rename, duplicate detection enhancements

## Open Items (from PRD Section 15)
1. Entra ID Tenant ID and SSO app registration — IT team
2. Ostrako NDA export format — Ostrako/IT team
3. Authorized senders for publication lists — Marketing Publications
4. Declined reason codes for Fundraise Leads (formerly Fund Prospects) — Product team
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
- `reference_data` table uses composite unique on `(category, value)` with optional `parent_value` for subtypes (e.g. activity subtypes scoped to parent type, lead stages scoped to lead_type)
- Person ↔ Org is a many-to-many via `person_organization_links` with `link_type` (primary/secondary/former) and `start_date`/`end_date` tracking
- Activity ↔ Org and Activity ↔ Person are separate junction tables
- Tags are polymorphic: `record_tags` has `record_type` + `record_id` columns
- Tasks are polymorphic: `linked_record_type` + `linked_record_id`
- `pg_trgm` extension enabled for fuzzy duplicate detection on org names and person names
- Full-text search index on `activities.details` using `to_tsvector('english', details)`
- All `updated_at` columns have `BEFORE UPDATE` triggers via `update_updated_at()` function
- Distribution lists have `l2_superset_of` self-referencing FK for L2→L1 enforcement
- 4 funds seeded: APC, CAPIX, CAPVX, HEDGX
- **Hybrid EAV:** `field_definitions` table stores metadata for all entity fields (core_column + eav storage types). `entity_custom_values` stores EAV field values with typed columns (value_text, value_number, value_date, value_boolean, value_json). Core columns remain on entity tables for performance; custom fields use EAV.
- **Multi-role auth:** `roles` table with JSONB `permissions` column; `user_roles` junction table for many-to-many user↔role assignment. 6 system roles seeded.
- **Lead owners:** `lead_owners` junction table allows multiple owners per lead with `is_primary` flag. Replaces single `aksia_owner_id` (kept for backward compat).
- **Leads unify advisory + fundraise + product:** `lead_type` discriminator column. Fundraise-specific columns (fund_id, share_class, target_allocation_mn, etc.) added directly to leads table. `fund_prospects` table kept as legacy backup.
- **Page layouts:** `page_layouts` table stores JSONB section configurations per entity (admin-editable via layout designer).
- **Saved views:** `saved_views` table stores per-user column/filter/sort configurations per entity type. Supports shared views.
- **Duplicate suppressions:** `duplicate_suppressions` table stores acknowledged non-duplicate pairs, filtered out of future duplicate checks. Normalized: smaller UUID always stored as `record_id_a`.
- **Documents:** `documents` table stores file metadata (entity_type + entity_id polymorphic). Actual files served via file_url.

## Key Architecture (Post-Patrick Plan)
These are the major systems introduced during the Patrick Implementation Plan (Phases 0–5). Understanding these is critical for working on the codebase.

### Dynamic Form System (`services/form_service.py`)
All 6 entity forms (Tasks, Activities, Contracts, People, Organizations, Leads) are rendered dynamically from `field_definitions` metadata. Key functions:
- `build_form_context(entity_type, record)` — loads field defs, groups by section, resolves dropdown options
- `parse_form_data(entity_type, form_data, field_defs)` — replaces per-router hardcoded form parsing
- `validate_form_data(entity_type, data, field_defs)` — field-level validation from metadata
- `save_record(entity_type, data, field_defs, record_id)` — splits core vs EAV, writes both
- Visibility rules in field_definitions JSONB: `when`/`equals`/`not_equals`/`in`/`not_in`/`min_stage`/`lead_type`
- Entity-specific UI (autocompletes, linked records, DNC, Lead→Contract) preserved alongside dynamic fields

### Reusable Grid (`services/grid_service.py`)
All 7 entity list pages use `build_grid_context()` instead of custom query logic. Key features:
- `_execute_query()` — Supabase query with entity-aware filters, sort, pagination, soft-delete filter
- `_enrich_rows()` — 7 entity-specific enrichment functions with batch resolution (no N+1)
- `_VIRTUAL_COLUMNS` — computed columns like `active_leads_count` on organizations
- Saved views — per-user column/filter/sort presets via `saved_views` table
- Column selector — Alpine.js dropdown with field grouping

### Admin Panel (`routers/admin.py`)
Full admin control panel with 6 sections (sidebar links visible to admin role only):
- **Fields:** CRUD for `field_definitions` per entity. System fields protected from deletion.
- **Layouts:** Page layout designer with JSONB section management.
- **Roles:** Role CRUD with entity permissions grid (6 entities × 6 actions). System roles protected.
- **Users:** Inline role assignment, activate/deactivate.
- **Reference Data:** CRUD for all 16 reference_data categories, hierarchical data support.
- **Duplicates:** Admin batch scan for orgs/people, similarity table, suppress button.

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

### Session 11 — March 12, 2026
- Built full Dashboards module: router (9 routes, 4 dashboards, all aggregation logic), 10 templates (4 full pages, 4 widget partials, 2 content partials)
- **Personal Dashboard** (homepage `/`): 4 HTMX lazy-loading widgets — Pipeline Summary (4 KPI cards by stage), My Open Tasks (10 items, overdue highlighting), My Open Leads (10 items, stage badges, revenue), My Recent Activities (10 items, type badges, linked orgs). All use `hx-trigger="load"` with skeleton loaders.
- **Advisory Pipeline Dashboard** (`/dashboards/advisory-pipeline`): 6 sections — KPI summary row (active leads, pipeline revenue, yr1 FLAR, win rate), Pipeline by Stage (horizontal CSS bars), Revenue by Service Type (horizontal bars), FLAR Analysis by Asset Class (table), Win/Loss Funnel (visual), Owner Coverage (table). Full HTMX filter bar (service type, asset class, owner, org type, date range) with partial swap on `#pipeline-content`.
- **Capital Raise Dashboard** (`/dashboards/capital-raise` and `/dashboards/capital-raise/{ticker}`): Fund selector tabs (All / APC / CAPIX / CAPVX / HEDGX), Allocation Progress (3 progress bars: target/soft/hard), Pace-to-Target indicator (green/yellow/red), Pipeline by Stage (10 stages), Investor Breakdown by LP Type (table), Declined Prospects (table). Handles NULL `target_raise_mn` gracefully.
- **Management Dashboard** (`/dashboards/management`): Admin-only via `require_role`. 5 sections — Firm-Wide KPIs (advisory pipeline + fundraising + FLAR + contracts revenue), Per-Fund Progress (4 mini progress bars), Quarter-over-Quarter (leads/revenue/fund prospects with delta arrows), Team Activity (activities per user last 30d), Data Quality Alerts (missing fields on leads/contacts).
- Updated `main.py` homepage route: added `current_user` dependency injection so personal dashboard widgets can filter by user
- Updated `base.html` sidebar: added "Management" link visible only to admin role (`{% if user is defined and user.role == 'admin' %}`)
- All visualizations are pure HTML + Tailwind CSS — no JavaScript charting libraries
- Each router is self-contained — helpers (`_batch_resolve_users`, `_is_overdue`, etc.) replicated inside `dashboards.py`
- Asset class filter on advisory pipeline uses post-query Python filtering (Supabase array contains is tricky with supabase-py)
- Org type filter on advisory pipeline uses two-step query: first find matching org IDs, then filter leads
- `not_.in_()` used for excluding inactive stages on leads widget (supabase-py syntax for NOT IN)
- Next step: Admin module

### Session 12 — March 13, 2026 (Power User Feedback Round)
- Implemented 6 feature enhancements based on power user feedback, logged to feedback.md
- **Activities — Org People Quick-Add + Auto-Add Primary Org:**
  - New `GET /activities/org-people?org_id=X` endpoint returns people at an org as quick-add suggestion buttons (blue-styled)
  - New `GET /activities/person-primary-org?person_id=X` endpoint returns JSON with primary org ID/name
  - `addOrg()` JS now fires HTMX load of org's people into `#org-people-suggestions` panel
  - `addPerson()` JS now auto-fetches and adds the person's primary org chip
  - Route ordering: org-people and person-primary-org placed after search-people, before subtypes
- **Activities — "My Activities" View:**
  - New `GET /activities/my-activities` endpoint with multi-step coverage query: author activities UNION covered-people activities UNION covered-org activities
  - Coverage query: people where `coverage_owner = user` → `activity_people_links`, leads where `aksia_owner_id = user` → org → `activity_organization_links`
  - list.html updated with "My Activities" / "All Activities" toggle tabs using `view_mode` context var
  - `_list_table.html` updated with `base_url` variable for correct HTMX target URLs
- **Tasks — Coverage Owner Suggestions:**
  - Task form (`GET /tasks/new`) with `?linked_type=activity` now looks up coverage owners at the activity's linked orgs
  - Suggested assignees shown as clickable chips below "Assigned To" dropdown
- **Activities — Follow-Up Notes Required:**
  - Server-side validation in both `create_activity()` and `update_activity()`: follow_up_notes required when follow_up_required is checked
  - Client-side: `toggleFollowUp()` toggles `required` attribute and red asterisk on notes label
- **Dashboard — Follow-Up Notes Display:**
  - Tasks widget now includes `notes` and `source` in query
  - `_widget_tasks.html` shows truncated follow-up notes (80 chars) for activity_follow_up tasks
- **Distribution Lists — Member Search Filters:**
  - `search-people` endpoint now accepts `country`, `rel_type`, `fund` query params
  - Two-step org filter: find matching org IDs → find person IDs at those orgs → filter people query
  - Fund filter: cross-references `fund_prospects.fund_id` to find relevant orgs
  - `_tab_members.html` has 3 filter dropdowns above search; filter change triggers HTMX refresh
  - Filters work standalone (no search text required) or combined with name search
- **"My [Module]" Views:**
  - New `GET /organizations/my-organizations`: orgs via coverage on people + leads
  - New `GET /people/my-people`: `.eq("coverage_owner", user.id)`
  - New `GET /fund-prospects/my-fund-prospects`: `.eq("aksia_owner_id", user.id)`
  - Each module's list.html has "My X" / "All X" toggle tabs with `view_mode` context
  - Each `_list_table.html` uses `base_url` variable for HTMX URLs
  - All `/my-*` routes ordered BEFORE `/{id}` routes
  - Sidebar links updated: Organizations → /my-organizations, People → /my-people, Activities → /my-activities, Fund Prospects → /my-fund-prospects
- **Dashboard — Personalized Coverage Insights (3 new widgets):**
  - `GET /dashboards/personal/widgets/my-coverage`: 2x2 grid showing counts of orgs/people/leads/fund prospects under coverage, each linking to the "My" view
  - `GET /dashboards/personal/widgets/missing-info`: people missing email/phone + leads missing revenue/service_type, top 5 each with edit links
  - `GET /dashboards/personal/widgets/stale-contacts`: people with no activity in 90+ days, batched activity date lookup, sorted by staleness, primary org resolution
  - 3 new widget templates: `_widget_my_coverage.html`, `_widget_missing_info.html`, `_widget_stale_contacts.html`
  - `index.html` dashboard layout expanded: added "My Coverage + Missing Info" row and "Stale Contacts" row
  - "View All" links on existing widgets updated to point to "My" module URLs
- Next step: Admin module

### Session 13 — March 15, 2026 (Phase 2: Merge Fund Prospects into Leads)
- Executed Phase 2 from Patrick Implementation Plan — merged Fund Prospects module into Leads via `lead_type` discriminator column
- **Step 2.1 — Schema changes:** Added 9 columns to `leads` table (lead_type, fund_id, share_class, decline_reason, target_allocation_mn, soft_circle_mn, hard_circle_mn, probability_pct, stage_entry_date). Added `idx_leads_type` index. Seeded `lead_type` reference_data category (advisory/product/fundraise) and fundraise-scoped `lead_stage` values via `parent_value`
- **Step 2.2 — Migration script:** Created `scripts/migrate_fund_prospects.py` — idempotent dry-run/apply script using `[migrated:fp:<uuid>]` marker in summary field for dedup. Migrates fund_prospect rows to leads with lead_type='fundraise', creates lead_owners, updates tasks/record_tags/audit_log references
- **Step 2.3 — Codebase cleanup:**
  - Removed fund_prospects router from `main.py` and sidebar from `base.html`
  - Major rewrite of `routers/leads.py`: lead_type branching in `_build_lead_data_from_form()`, `_validate_lead_fields()`, `_load_form_context()`, all CRUD routes; fundraise stage constants; fund enrichment helpers; scoped stage loading by parent_value
  - Updated `routers/dashboards.py`: Capital Raise + Management dashboards query leads instead of fund_prospects; backward-compatible batch_resolve for legacy `fund_prospect` linked records
  - Updated `routers/tasks.py`: linked record resolution checks leads first, falls back to fund_prospects for unmigrated records
  - Updated `routers/organizations.py` + templates: "Fund Prospects" tab → "Fundraise Leads" tab; created `_tab_fundraise_leads.html`
  - Rewrote all lead templates (form.html, detail.html, list.html, _list_table.html) for dual advisory/fundraise support with JS toggles and conditional sections
  - Updated `scripts/seed_data.py`: replaced `seed_fund_prospects()` with `seed_fundraise_leads()` creating leads with lead_type='fundraise' + lead_owners rows; updated task seeding to use `linked_record_type='lead'` and `source='lead_next_steps'`
- **Step 2.4 — Field definitions:** Added lead_type + 8 fundraise fields to LEAD_FIELDS in `seed_field_definitions.py`; removed standalone FUND_PROSPECT_FIELDS entity
- Key decisions: fund_prospects table NOT dropped (kept as backup); lead_type locked after creation; stages scoped via parent_value on reference_data; dashboard code normalizes rating→stage for template compatibility
- Next step: Phase 3 (Admin Control Panel)

### Session 14 — March 15, 2026 (Phase 3: Admin Control Panel)
- Executed Phase 3 from Patrick Implementation Plan — Admin Control Panel (Changes 10.1, 10.2, 10.3)
- **Step 3.1 — Field Management:**
  - Rewrote `routers/admin.py` from stub: field list/create/edit/toggle/reorder endpoints, HTMX partials
  - Created `templates/admin/fields.html` (entity type selector, field list), `templates/admin/_field_list_partial.html` (HTMX partial with section grouping, badges, reorder buttons), `templates/admin/field_form.html` (create/edit with system field restrictions)
  - System fields (`is_system=true`) protected: cannot delete, cannot change field_name/storage_type/field_type
- **Step 3.2 — Dynamic Form Rendering:**
  - Created `services/form_service.py`: `build_form_context()`, `parse_form_data()`, `validate_form_data()`, `save_record()`, `_is_field_visible()` with visibility rules (when/equals/not_equals/in/not_in/min_stage/lead_type)
  - Created `templates/components/_field_renderer.html`: Jinja2 macro rendering 12 field types (text, textarea, email, url, phone, number, currency, date, boolean, dropdown, multi_select, lookup) with data-vis-* attributes
  - Created `templates/components/_form_section.html`: section card macro with grid layout, full-width for textareas
  - Migrated all 6 entity forms to dynamic rendering: Tasks, Activities, Contracts, People, Organizations, Leads
  - Each router now uses `build_form_context()` + `parse_form_data()` + `validate_form_data()` while preserving entity-specific UI (autocompletes, linked records, DNC, Lead→Contract promotion, etc.)
- **Step 3.3 — Page Layout Designer:**
  - Added `page_layouts` table to `db/schema.sql` (entity_type, layout_type, sections JSONB, is_active)
  - Added layout CRUD endpoints to `routers/admin.py`
  - Created `templates/admin/layout_designer.html` with modal form and dynamic section management
- **Step 3.4 — Role + User Management:**
  - Added role CRUD endpoints to `routers/admin.py` with entity permissions grid (6 entities x 6 actions) + admin permissions
  - Created `templates/admin/roles.html` (list with system/custom badges), `templates/admin/role_form.html` (permissions grid)
  - Rewrote `templates/admin/users.html` with inline role assignment, activate/deactivate
  - System roles protected from deletion/rename
- Updated `base.html` sidebar: Admin section with Roles, Fields, Layouts links (visible to admin role only)
- All 11 Python files + 10 templates syntax-verified
- Next step: Phase 4 (Reusable Grid Component) — prompt saved to `echo2/Phase_4_Prompt.md`

### Session 15 — March 15, 2026 (Phase 4: Reusable Grid Component)
- Executed Phase 4 from `echo2/Phase_4_Prompt.md` — replaced all 7 entity list pages with a unified reusable grid component
- **Step 4.1 — Schema:** Added `saved_views` table to `db/schema.sql` (user_id, entity_type, view_name, columns JSONB, filters JSONB, sort_by, sort_dir, is_default, is_shared) with `idx_sv_user_entity` index
- **Step 4.2 — Grid Service:** Created `services/grid_service.py` (~600 lines) — central replacement for per-router list logic:
  - `build_grid_context()`: main entry point, returns dict with columns, rows, pagination, sort, filters, saved_views, grid_container_id, field_defs
  - `_execute_query()`: Supabase query with entity-aware filters, sort, pagination
  - `_apply_filters()`: handles text search, entity-specific dropdown filters, date ranges, privacy filters (dist lists), ID-scoped filters (`_org_ids`, `_activity_ids`)
  - `_enrich_rows()`: dispatches to 7 entity-specific enrichment functions using batch resolution (no N+1)
  - `save_view()`, `delete_view()`, `set_default_view()`: saved views CRUD
  - Constants: `_ENTITY_TABLES`, `_DEFAULT_COLUMNS`, `_BASE_SELECT`, `_VALID_SORT`, `_DEFAULT_SORT` for all 7 entities
- **Step 4.3 — Grid Template:** Created `templates/components/_grid.html` (~400 lines):
  - Saved view selector dropdown (Alpine.js), column selector, page size selector
  - Data table with sortable HTMX column headers (click toggles asc/desc)
  - Entity-specific cell rendering: status/stage/type badges, currency formatting, date formatting, linked record links, action buttons
  - Empty state with entity-specific messaging
  - Pagination with page numbers, prev/next, all via HTMX partial swap
  - Save View modal (name input, save button posting to `/views/save`)
- **Step 4.4 — Column Selector:** Created `templates/components/_column_selector.html` — Alpine.js dropdown with checkboxes grouped by section, All/None toggles, Apply button fires HTMX reload with `visible_columns` param
- **Step 4.5 — Views Router:** Created `routers/views.py` — `POST /views/save`, `POST /views/{id}/delete`, `POST /views/{id}/set-default`; registered in `main.py`
- **Step 4.6 — All 7 Entity Routers Updated:**
  - Organizations: `my_organizations` pre-computes org IDs via coverage, passes as `extra_filters={"_org_ids": ...}`
  - People: `my_people` queries by coverage_owner, passes ID list
  - Leads: handles `lead_type` + `view=my` via extra_filters
  - Activities: `my_activities` does multi-step coverage query (author + covered people + covered orgs), passes `_activity_ids`
  - Tasks: `my_tasks` passes `extra_filters={"assignee": user.id}`
  - Contracts: simple delegation, no "My" view
  - Distribution Lists: passes `_user_id`/`_user_role` for privacy filtering
- **Step 4.7 — All 7 list.html Templates Updated:** Old `_list_table.html` includes replaced with `{% include "components/_grid.html" %}`, HTMX targets updated to `#{{ grid_container_id }}`
- **Cleanup:** Deleted 8 old `_list_table.html` partials (7 entities + legacy fund_prospects)
- Grid container IDs: `f"{entity_type.replace('_', '-')}-grid-container"` prevents HTMX target conflicts
- Distribution lists: dual official/custom sections collapsed into single grid (privacy handled by grid_service)
- Next step: Test by running server, then Reference Data management or SSO/Auth

### Session 16 — March 15, 2026 (Phase 5: Remaining Changes)
- Executed Phase 5 from `echo2/Phase_5_Prompt.md` — all 7 steps implementing Changes 9, 11, 12, 13, 14, 15 + Reference Data Admin CRUD
- **Step 5.0 — Reference Data Admin CRUD:**
  - 8 endpoints in `routers/admin.py`: list categories, list values, create/edit/update/toggle/reorder values
  - `_CATEGORY_META` dict for 16 categories with labels and parent_category relationships
  - 3 templates: `reference_data.html` (two-column layout), `_reference_data_values.html`, `_reference_data_form.html`
  - Hierarchical support: `activity_subtype` → `activity_type`, `lead_stage` → `lead_type` via `parent_value`
  - All endpoints HTMX-partial-aware
- **Step 5.1 — Lead Finder + Grid Virtual Columns:**
  - `_VIRTUAL_COLUMNS` dict in `services/grid_service.py` with `active_leads_count` for organization entity
  - `_enrich_organizations()` batch-queries active leads count per org
  - `build_grid_context()` merges virtual columns into field_defs
  - Seed SQL for "Lead Finder" shared saved view (commented, ready to apply)
- **Step 5.2 — Contract Creation from Won Leads:**
  - Removed `_promote_lead_to_contract()` auto-promotion from `routers/leads.py`
  - Added `GET /contracts/new` (pre-filled from lead) and `POST /contracts/create` to `routers/contracts.py`
  - `contracts/form.html` now supports both create and edit modes
  - Lead detail shows "Create Contract" button for won leads without existing contract
- **Step 5.3 — Distribution List + Follow-Up Enhancements:**
  - `POST /{list_id}/remove-member` and `POST /{list_id}/add-filtered` endpoints in `routers/distribution_lists.py`
  - Distribution list membership tab on person detail (`people/_tab_distribution_lists.html`)
  - "Assign Follow-Up To" dropdown on activity form; `_create_follow_up_task()` accepts `assignee_id` param
- **Step 5.4 — Organization Leads Panel:**
  - `GET /organizations/{org_id}/leads-panel` endpoint returns mini-table of active leads
  - `_org_leads_panel.html` template; `_grid.html` renders expandable leads panel on `active_leads_count` cells
- **Step 5.5 — Soft Delete Rename (`is_archived` → `is_deleted`):**
  - Global rename across 10 routers, 8 Pydantic models, grid_service.py, seed_data.py, migrate_fund_prospects.py
  - 11 ALTER TABLE RENAME COLUMN statements in schema.sql
  - `duplicate_suppressions` table added to schema.sql
  - Admin restore endpoint: `POST /admin/{entity_type}/{record_id}/restore` with audit logging
  - `fund_prospects.py` intentionally kept with `is_archived` (legacy backup, not actively used)
  - CLAUDE.md Database Rules updated to reference `is_deleted`
- **Step 5.6 — Duplicate Detection Enhancements:**
  - Suppression filtering in `_check_duplicates()` for both orgs and people — queries `duplicate_suppressions` table, filters both directions (a→b, b→a)
  - `POST /organizations/{org_id}/suppress-duplicate` and `POST /people/{person_id}/suppress-duplicate` — normalize UUIDs (smaller as record_id_a), upsert suppression, audit log, return updated warning partial
  - Updated `_duplicate_warning.html` templates: "Not a Duplicate" button per match row (HTMX-powered, swaps `#duplicate-warning` div)
  - Admin batch scan: `GET /admin/duplicates/{entity_type}` — iterates all active records, calls existing similarity RPCs, excludes suppressed pairs, sorts by similarity desc, paginated (50/page, capped at 200 pairs)
  - `POST /admin/duplicates/{entity_type}/suppress` — admin suppress from scan page, returns empty HTML to remove row
  - `templates/admin/duplicates.html` — org/person tabs, similarity table with color-coded scores (red ≥80%, yellow ≥60%), empty state
  - Sidebar "Duplicates" link added under Admin section
  - Merge endpoint deferred as stretch goal per prompt spec
- All 15 architectural changes from Patrick Implementation Plan now implemented across Phases 0–5
- Next step: SSO/Auth (Microsoft Entra ID) or manual testing + data migration

### Session 17 — March 15, 2026 (Post-Migration Debugging + CLAUDE.md Update)
- Updated CLAUDE.md to reflect all Patrick Implementation Plan changes (Phases 0–5): project structure, multi-role auth, schema design decisions, key architecture sections, coding standards
- Debugged dashboard/list page 500 errors (`column X.is_archived does not exist`) after running `migrate_schema.sql`
- Source code was correct (`is_deleted` everywhere) but browser was getting errors referencing `is_archived`
- Root cause: old uvicorn processes still running on the same port. Windows allows multiple processes to bind to the same port via SO_REUSEADDR. The browser was hitting the OLD server with pre-Phase 5 code, not the restarted one.
- **Dev workflow rule:** Before restarting the server on Windows, always kill ALL existing Python/uvicorn processes first. Use `tasklist | grep python` and `netstat -ano | grep :800` to verify. A fresh `uvicorn` start succeeding does NOT mean old servers are gone.

### Session 18 — March 15, 2026 (Final Feedback Round — 8 Items)
- Implemented 8 feedback items: 4 bug fixes + 4 feature enhancements
- **Bug Fix: Alpine.js missing** — Added Alpine.js CDN to `base.html` + `[x-cloak]` CSS to `custom.css`. Column selector and saved views dropdowns were always visible because Alpine.js directives were silently ignored without the library.
- **Bug Fix: Person dead link** — Removed generic `onclick` on line 130 of `_grid.html` that generated `/persons/{id}` instead of `/people/{id}`. HTML uses the FIRST attribute when duplicates exist, so entity-specific overrides were ignored.
- **Bug Fix: Distribution lists empty** — Added `DISTRIBUTION_LIST_FIELDS` (10 fields) to `seed_field_definitions.py` and re-seeded. Grid depends on field_definitions for column metadata.
- **Bug Fix: Required fields togglable** — Updated `_column_selector.html` to lock required fields (`is_required=True`) as checked+disabled, with exceptions: org can toggle relationship_type/organization_type, lead can toggle rating/share_class, task can toggle assigned_to/status.
- **Dashboard customizable views** — Added group-by selector dropdowns to Advisory Pipeline and Capital Raise dashboards. Users can switch between grouping dimensions (stage, service_type, asset_class, owner, fund). Added drill-down: clicking a bar opens a table of matching leads. New endpoints: `GET /dashboards/advisory-pipeline/chart`, `/drilldown`, `GET /dashboards/capital-raise/chart`, `/drilldown`. New templates: `_advisory_chart.html`, `_advisory_drilldown.html`, `_capital_raise_chart.html`, `_capital_raise_drilldown.html`.
- **Vertical funnel charts** — Replaced horizontal bar/box funnels with CSS `clip-path: polygon()` trapezoid shapes. Reusable `_funnel.html` partial. Funnel CSS in `custom.css`. Advisory funnel: Total → Active → Won → Lost. Capital raise funnel: Total → Active → DD+ → Soft Circle+ → Closed.
- **Per-column filters** — Added filter icon to each column header with data-type-specific filter dropdowns (multi-select checkboxes for dropdowns, contains/not-contains for text, inequality operators for numbers, date pickers for dates, yes/no for booleans). URL format: `cf_<field>=<op>:<value>`. Removed entity-specific filter dropdowns from all 7 list templates, kept search box only. New template: `_column_filter.html`. New functions in `grid_service.py`: `_extract_column_filters()`, `_apply_column_filters()`.
- **Screeners** — Renamed "Saved Views" to "Screeners" throughout UI. Added overwrite, duplicate, and rename capabilities. 3 new endpoints in `views.py`: `POST /{id}/overwrite`, `/duplicate`, `/rename`. 3 new functions in `grid_service.py`: `update_view()`, `duplicate_view()`, `rename_view()`. Hover-revealed action buttons per screener in dropdown.
- All feedback logged in `feedback.md` under "Final Feedback — Round 4"

### Session 19 — March 16, 2026 (Feedback Round — 6 Items)
- Implemented 6 feedback items: 1 bug fix + 5 feature enhancements
- **Bug Fix: 500 error on field creation** — `AttributeError: 'NoneType' object has no attribute 'data'` at `admin.py:213`. Root cause: `maybe_single().execute()` can return `None` when no rows match. Fixed 3 duplicate-check guards (`if dup.data:` → `if dup and dup.data:`) for field, role, and reference data creation. Also added defensive `if not resp or not resp.data:` guards on ~13 by-ID lookups throughout `admin.py`.
- **Distribution Lists split views** — Split into Official and Custom/Private tabs, defaulting to Custom/Private. Added `list_view` query param (`custom`/`official`). Official tab shows all official lists (visible to everyone). Custom tab shows non-official lists with privacy filter for non-admins. Removed `is_official` from default grid columns. Updated `_apply_filters()` in `grid_service.py` to handle `_list_view` filter. Added `list_view` as a filter alias so it persists across HTMX sort/pagination/search requests.
- **Required columns pinned left** — Added `_pin_required_columns_left()` function in `grid_service.py` with togglable exceptions dict (`_TOGGLABLE_EXCEPTIONS`). Called in `_resolve_visible_columns()` to enforce required-first ordering on all column lists (from URL params, saved views, and defaults). Frontend `applyColumns()` also enforces this order.
- **Save Screener always visible** — The screener dropdown (`{% if saved_views %}`) was hiding the entire UI including "Save as Screener" when no views existed. Added `{% else %}` block with standalone "Save Screener" button so users can always create their first screener.
- **Column reordering** — Complete rewrite of `_column_selector.html` using Alpine.js reactive component (`columnSelector()`). Required columns rendered at top (locked, no arrows, always checked). Optional columns shown below with visibility checkboxes and up/down arrow buttons for reordering. Arrows appear on hover. Column order is preserved: visible optional columns maintain current display order, non-visible ones appear below. `applyColumns()` reads from Alpine array order. Section grouping removed in favor of flat reorderable list.
- **Funnel visualization fix** — Replaced CSS `clip-path: polygon()` trapezoid shapes (which created X/bowtie visual artifact) with proportional-width centered bars. Width decreases linearly from 100% (first stage) to 40% (last stage). Uses `rounded-lg` + `mx-auto` Tailwind classes. Removed old `.funnel-container` and `.funnel-stage` CSS rules from `custom.css`. Advisory funnel: 4 stages at 100%→80%→60%→40%. Capital raise funnel: 5 stages at 100%→85%→70%→55%→40%.
- **Follow-up fixes (4 items):**
  - **Columns/filters independence** — `visible_columns` was not included in the server-rendered HTMX links (`filter_qs`) for sort headers and pagination. Sorting or paginating would reset column selection to defaults. Fixed by adding `visible_columns` to `filter_qs` builder in `_grid.html`. Also excluded `cf_*` keys from the `filters` loop to prevent double-inclusion (they come from `col_filters` loop). When a column is removed via the column selector, any active `cf_*` filter on that column is now automatically cleared.
  - **Multiple column filters** — Multiple `cf_*` params were already supported by the JS (`applyColumnFilter` preserves all URL params via `window.location`) and server (`_extract_column_filters` parses all `cf_*` params). The fix above (preserving `visible_columns` in `filter_qs`) also ensures all `cf_*` params survive sort/paginate interactions via server-rendered links.
  - **Screener save includes column filters** — The save/overwrite forms were storing `{{ filters | tojson }}` which excluded `col_filters` (the `cf_*` params are in a separate dict). Added `merged_filters` template variable that combines non-`_` filters + `col_filters` into one dict. Used in both the save modal and overwrite form. The load path (`build_grid_context` lines 214-217) already restored `cf_*` keys from saved filters — only the save side was broken.
  - **Column reorder arrows always visible** — Removed `opacity-0 group-hover:opacity-100` from the arrow button container in `_column_selector.html` so up/down arrows are always visible, not just on hover.

### Session 20 — March 19, 2026 (Patrick Feedback Round 2 — 18 Items)
- Verified AI summary of Patrick stakeholder call against raw transcript (Patrick 2.vtt). Found 1 inaccuracy: multi-tenant labeled "Phase 1" in summary but Patrick said "Not Phase 1".
- Implemented 18 feedback items across 5 phases (A through E):
- **A3:** Custom EAV fields now render in all 5 entity edit forms (organizations, people, leads, activities, contracts). Added `split_core_eav()` helper to separate core vs EAV fields before DB operations. All create/update endpoints now save EAV values via `save_custom_values()`.
- **A1:** Removed sections from field definitions. Created `_group_fields_by_layout_or_fallback()` in form_service.py that uses `page_layouts` as authoritative source, falling back to `section_name`. Created `scripts/seed_default_layouts.py`. Removed section selector from admin field form.
- **A2:** Merged Reference Data into Fields page. Added inline dropdown value management per field via HTMX endpoints. Created `_inline_reference_data.html`. Removed Reference Data sidebar link.
- **A5:** Added visibility rules admin UI to `field_form.html` — configurable `when`/`equals`/`not_equals`/`in`/`not_in`/`min_stage`/`lead_type` conditions. Updated admin create/update endpoints to parse and save `visibility_rules`.
- **A4:** Added suggested fields concept. New `suggestion_rules` JSONB column on `field_definitions`. `_is_field_suggested()` evaluator in form_service. Amber border + "Suggested" badge in `_field_renderer.html`. Admin UI for suggestion conditions.
- **A6:** New `text_list` field type for multiple text strings (aliases/nicknames). Alpine.js multi-input in forms. Stored as JSON array in EAV `value_json`. Grid shows comma-separated values. Seeded `nicknames` field on organizations.
- **B1:** Cross-entity linked columns — org_city, org_country, org_type, org_aum_mn virtual columns on People/Leads grids. contact_count aggregate on Org grid. Expanded `batch_resolve_orgs()` select.
- **B2:** `has_active_leads` boolean virtual column on Org/People grids with pre-filter logic in `_execute_query()`. Moved `_INACTIVE_STAGES` to module-level constant.
- **B3:** Column resizing via draggable borders. CSS resize handles on `<th>` elements. JS `startColResize()`. Widths persisted to localStorage.
- **B4:** Pop-up row editor. New `_grid_edit_modal.html` template. `GET/POST /views/grid-edit/{entity_type}/{record_id}` endpoints in views.py. HTMX modal trigger on edit button. `gridRefresh` custom event for row update.
- **C1:** Advisory pipeline defaults to active leads only. Added `active_filter` (active/all/inactive) and `stage` filter params. Renamed "Active Leads" KPI to "Leads".
- **C2:** Dynamic pipeline grouping. `_get_groupable_fields()` queries `field_definitions` for dropdown/multi_select fields. Custom fields auto-appear in group-by dropdown.
- **C3:** Dashboard drill-down now uses full grid component via `build_grid_context()`. Added `grid_container_id_override` and `_lead_ids` filter support. Both advisory and capital raise drilldowns rewritten.
- **D1:** Dynamic distribution lists. Added `list_mode` (static/dynamic), `filter_criteria` JSONB, `is_manual` flag. `_resolve_dynamic_members()` applies people filters. `_build_send_preview()` handles dynamic membership.
- **D2:** Distribution list creation via people grid. Filter editor endpoint embeds people grid. Save filters as list criteria.
- **D3:** Real-time member list refresh. Added `HX-Trigger: membersUpdated` on add_member endpoint. `hx-trigger="membersUpdated from:body"` listener on members-content div.
- **E1:** Screener dropdown split into "My Screeners" / "Team Screeners" sections. Team screeners show owner name and only Duplicate action.
- **E2:** Navigation sidebar consolidated — Pipeline section merged into Records, Reference Data link removed.
- Deferred: multi-tenant architecture, generic calculated fields admin UI, duplicate detection merge, editable Excel-style grid
- **DB migration required:** Run the A4/A6/D1 block at the end of `migrate_schema.sql` in Supabase SQL Editor (suggestion_rules column, text_list CHECK constraint, list_mode/filter_criteria/is_manual columns). Also run `python -m scripts.seed_default_layouts` for A1 layout seeding.

### Session 20b — March 22, 2026 (Post-Implementation Bug Fixes)
- **Stale server issue:** Most reported bugs (10 items) were caused by a stale uvicorn process still bound to port 8000 from before the code changes. Windows allows multiple processes on the same port via SO_REUSEADDR. Fix: `taskkill //F //IM python.exe` before restarting.
- **DB migration not applied:** Distribution lists page 500'd because `list_mode` column didn't exist. Applied migration SQL in Supabase SQL Editor. Temporarily removed `list_mode`/`filter_criteria` from `_BASE_SELECT` until migration was confirmed, then re-added.
- **Bug fix: Has Active Leads filter key mismatch** — `_extract_column_filters()` keeps the `cf_` prefix on keys, but the pre-filter logic in `_execute_query()` was checking for `"has_active_leads"` without the prefix. Fixed to check `"cf_has_active_leads"`.
- **Bug fix: text_list Alpine.js quoting** — The `x-data` attribute used double quotes (`"{ items: ["a","b"] }"`), which broke when the JSON array contained strings with double quotes. Fixed to use single-quoted attribute (`x-data='{ "items": [...] }'`).
- **Enhancement: Custom EAV field section placement** — EAV fields now render in their correct section with "(custom)" italic label. Fields in sections not present in the hardcoded form are grouped under "Additional Custom Information". Updated all 5 entity form templates with `known_sections` list per entity.
- **Open item: Visibility conditions UI** — Patrick wants dropdown selectors instead of text inputs for configuring visibility rules. Functional with text inputs for now, dropdowns deferred to polish pass.

### Session 21 — March 25, 2026 (Patrick Feedback Round 3 — 8 Items)
- Source: Miles-Patrick call transcript (`Miles-Patrick final.vtt`) + AI summary (`Miles-Patrick Final Feedback Summary.docx`). Cross-referenced for accuracy.
- **Bug fix: Has Active Leads filter for People** — Pre-filter now handles People entity (org_ids → person_organization_links → person_ids). Also fixed `want_active=False` case for both orgs and people (was unfiltered). Widened link_type from `primary` to `["primary", "secondary"]`.
- **Bug fix: Dynamic distribution list preview/send** — Two issues: (1) `_resolve_dynamic_members()` crashed on org-level virtual column filters (`cf_org_country` etc.) because they don't exist on the `people` table. Fixed by separating org-level filters, pre-querying organizations, then constraining people by org links. (2) `_build_send_preview()` used N+1 `_get_person_with_org()` calls per member. Replaced with batch queries (3 queries total: people, person_org_links, organizations).
- **Enhancement: Dropdown values on field edit page** — Embedded `_inline_reference_data.html` partial into `field_form.html` via HTMX `hx-trigger="load"` for dropdown/multi_select fields in edit mode.
- **Enhancement: Section assignment in field editor** — Replaced the static "go to Layout Designer" text with a section dropdown populated from page_layouts (authoritative) + field_definitions (fallback). Both new and edit endpoints updated.
- **Enhancement: Dashboard drill-down — no column filters** — Added `hide_column_filters` flag to `_grid.html`. Both advisory and capital raise drilldown endpoints pass `hide_column_filters=True`. Column selector and sort still work.
- **Enhancement: Distribution list — dynamic vs static member split** — Dynamic lists now show two sections on the detail page: "Dynamic Members" (resolved from filter criteria, blue header, paginated to 25) and "Manual Additions" (static members, amber header). Detail endpoint resolves dynamic members via batch queries.
- **Enhancement: Linked org field column filters** — Virtual columns `org_city`, `org_country`, `org_type`, `org_aum_mn` on People and Leads grids now filterable. Added pre-query logic in `_execute_query()` that queries organizations table first, then constrains the main query via person_organization_links (people) or organization_id FK (leads).
- **Feature: Calculated/linked fields (admin-configurable)** — Patrick's key architectural ask. New `storage_type='linked'` option on field_definitions with `linked_config` JSONB column storing `{source_entity, source_field, link_via}`. Admin UI shows source entity/field/link-via dropdowns when storage_type=linked. Grid service resolves linked fields dynamically via `_resolve_linked_fields()` (batch queries grouped by source). Pre-query column filtering extended to dynamically include admin-configured linked fields. Form service marks linked fields as read-only and skips them during parse/save.
- **DB migration required:** Run `ALTER TABLE field_definitions ADD COLUMN IF NOT EXISTS linked_config JSONB;` in Supabase SQL Editor (added to `migrate_schema.sql`).
- Existing hardcoded `_VIRTUAL_COLUMNS` kept for backward compatibility — admin-created linked fields supplement them. The linked field resolver checks `if fd["field_name"] not in row` to avoid overwriting entity-specific enrichment.
- Next step: Load real Echo data (5K orgs, 12K contacts, 2.4K leads) to test the system with production-scale data.

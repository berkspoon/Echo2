# Echo 2.0 — CRM for Aksia

## Project Overview
Echo 2.0 is a purpose-built CRM system for Aksia, an investment management and advisory firm. It replaces the current Microsoft Power Apps-based "Echo" platform. The PRD (Echo_2.0_PRD_v1.0.docx) is the source of truth for all product decisions.

## Tech Stack
- **Backend:** FastAPI (Python 3.12)
- **Templating:** Jinja2 (server-side HTML — no frontend framework)
- **Frontend interactivity:** HTMX (loaded via CDN), Alpine.js (loaded via CDN)
- **Styling:** Tailwind CSS (loaded via CDN — no build step, no Node.js)
- **Database:** Supabase (PostgreSQL) via supabase-py
- **Authentication:** Microsoft Entra ID SSO via MSAL (dev stub until SSO wired up)
- **Hosting:** Railway
- **No Node.js. No npm. No React. No Next.js. No frontend build pipeline of any kind.**

## Project Structure
```
echo2/
├── main.py                  # FastAPI app, 12 routers mounted
├── config.py                # pydantic-settings v2 (model_validator for entra_authority)
├── dependencies.py          # Auth: CurrentUser (multi-role), get_current_user, require_role
├── routers/
│   ├── organizations.py     # Orgs CRUD, duplicate detection, coverage rollup
│   ├── people.py            # People CRUD, DNC enforcement, duplicate detection
│   ├── activities.py        # Activities CRUD, follow-up task generation
│   ├── leads.py             # Advisory + fundraise + product lead types
│   ├── contracts.py         # Legal-only edit, fee arrangements CRUD
│   ├── distribution_lists.py # Static + dynamic lists, filter builder, send preview
│   ├── tasks.py             # My Tasks/All Tasks, polymorphic record linking
│   ├── dashboards.py        # 4 dashboards: Personal, Advisory, Capital Raise, Management
│   ├── admin.py             # Fields, layouts, roles, users, duplicates, view configs
│   ├── documents.py         # Document metadata
│   ├── views.py             # Screeners CRUD, bulk edit/delete, export
│   └── fund_prospects.py    # LEGACY BACKUP — NOT mounted, do not use
├── services/
│   ├── form_service.py      # Dynamic form build/parse/validate/save from field_definitions
│   └── grid_service.py      # Reusable grid: query, enrich, paginate, screeners, export
├── db/
│   ├── client.py            # Supabase client singleton
│   ├── schema.sql           # Full schema (30+ tables)
│   ├── migrate_schema.sql   # Idempotent migration (Phases 1–6)
│   ├── field_service.py     # EAV field definitions + custom values
│   ├── view_config_service.py # Admin view configurations (TTL-cached, validated, audited)
│   └── helpers.py           # Shared DB helpers (audit, reference_data, batch resolve)
├── scripts/
│   ├── seed_data.py         # Dummy data (~3,400 rows): python -m scripts.seed_data [--force]
│   ├── seed_field_definitions.py  # Field defs for all 6 entities
│   ├── seed_default_layouts.py    # Default page layouts
│   ├── seed_view_configurations.py # View configs (13 rows): python -m scripts.seed_view_configurations
│   └── migrate_fund_prospects.py  # One-time: fund_prospects → leads
├── templates/
│   ├── base.html            # Sidebar nav, HTMX + Tailwind + Alpine.js CDNs
│   ├── index.html           # Personal dashboard (7 HTMX lazy-load widgets)
│   ├── components/          # _grid.html, _column_selector.html, _field_renderer.html, _form_section.html
│   ├── organizations/ people/ activities/ leads/ contracts/ distribution_lists/ tasks/
│   ├── dashboards/          # 4 pages + widget/content partials
│   └── admin/               # fields, layouts, roles, users, duplicates, views
└── static/css/custom.css
```

## Two Business Lines
1. **Advisory / Discretionary / Research** — relationship-driven, institutional clients. Pipeline: Leads → Contracts. Revenue metric: FLAR (base advisory fees only).
2. **Products / ACPM** — fundraising for commingled funds. Pipeline: Leads with `lead_type='fundraise'|'product'`. Funds: APC, CAPIX, CAPVX, HEDGX.

## User Roles & Permissions
| Role | Key Permissions |
|------|----------------|
| Admin | Full access. User/role/field management, audit log, duplicate merge. |
| Legal | View all. Create/edit Contracts only. |
| RFP Team | Standard access + RFP Hold toggle on Organizations. |
| BD | Standard access + lead ownership. |
| Standard User | CRUD on Orgs, People, Activities, Leads. No Contracts, RFP Hold, or hard-delete. |
| Read Only | View and export only. |

- Multi-role system via `user_roles` junction table. Permissions additive. 6 system roles (cannot delete/rename).
- `require_role()` checks `any(r in allowed_roles for r in user.roles)`
- Currently using dev stub user — SSO awaiting IT app registration.

## Database Rules — Always Follow
- Soft deletes only: `is_deleted BOOLEAN DEFAULT FALSE`. Never SQL DELETE. Always filter `WHERE is_deleted = FALSE`.
- Audit every field change to `audit_log` table.
- Dropdown values NEVER hardcoded — always from `reference_data` table by category.
- Every table has `id UUID`, `created_at`, `updated_at`, `created_by`.

## Key Business Logic — Always Follow
- **Do Not Contact:** Auto-remove from all distribution lists + suppress from sends.
- **RFP Hold:** Suppress org's contacts from DL send previews (not removed from lists).
- **L2 superset of L1:** L2 publication list members auto-receive L1 content.
- **Lead → Contract:** Manual creation only (no auto-promotion). "Create Contract" button on Won leads.
- **Coverage:** Stored at Contact + Lead level. Org page shows read-only rollup.
- **Lead Types:** `lead_type` discriminates advisory/fundraise/product. Stages scoped via `parent_value`.
- **Next Steps Date:** Auto-generates Task assigned to lead owner.
- **Activity Follow-Up:** Auto-generates Task. Assignee selectable. Follow-up notes required when enabled.

## Coding Standards
- FastAPI dependency injection for auth on every route
- All DB queries through `db/client.py` — never import supabase directly
- Use `db/helpers.py` shared helpers — never duplicate audit/resolve functions
- Use `form_service.py` for forms, `grid_service.py` + `build_grid_context()` for lists
- HTMX: return partials when `HX-Request` header present, full pages otherwise
- Route ordering: static paths (`/new`, `/my-tasks`) BEFORE `/{id}` catch-all

## Key Architecture

### Dynamic Forms (`services/form_service.py`)
All 6 entity forms render from `field_definitions`. Functions: `build_form_context()`, `parse_form_data()`, `validate_form_data()`, `save_record()`. Visibility rules: `when`/`equals`/`in`/`not_in`/`min_stage`/`lead_type`. Suggestion rules for amber-highlighted fields.

### Reusable Grid (`services/grid_service.py`)
All 7 entity list pages use `build_grid_context()`. Features: entity-aware query/filter/sort/pagination, batch enrichment (no N+1), virtual columns (`_VIRTUAL_COLUMNS`), admin-created linked fields, screeners (saved views), per-column filters (`cf_*` URL params), bulk edit/delete, Excel export, column resizing.

### Admin Panel (`routers/admin.py`)
7 sections: Fields, Layouts, Views, Roles, Users, Reference Data (inline on fields), Duplicates.

### View Configurations (`db/view_config_service.py`)
Admin-configurable settings for DL filters, dashboard table columns, group-by/metric options, grid defaults. 13 seed configs across 3 categories (distribution_lists, dashboards, grids). TTL-cached (60s), validated on save, audit-logged, resettable to defaults. Admin UI at `/admin/views` with visual builders (column, option list, grid picker, DL filter editor).

### Schema Design
- Hybrid EAV: `field_definitions` (metadata) + `entity_custom_values` (typed value columns). Core columns on entity tables for performance.
- `reference_data`: composite unique `(category, value)` with `parent_value` for subtypes.
- Person ↔ Org: many-to-many via `person_organization_links` with link_type + date tracking.
- Tasks + Tags: polymorphic via `record_type` + `record_id`.
- Distribution lists: `l2_superset_of` self-FK, `list_mode` (static/dynamic), `filter_criteria` JSONB.
- Leads: `lead_type` discriminator. Fund_prospects table kept as legacy backup only.
- `pg_trgm` for fuzzy duplicate detection. Full-text search on activities.

## Build Status
All core modules complete. Phases 0–6 done. Data migration complete (Steps 0-7).

### Done
- [x] All 12 entity modules (orgs, people, activities, leads, contracts, DLs, tasks, dashboards, admin, documents, views, fund_prospects)
- [x] Data import: 5,383 orgs, 12,912 people, 2,804 leads, 404 contracts, 27,371 activities, 10,717 DL memberships, 17,152 coverage owners — all validated with 0 FK orphans
- [x] V17 lead field restructuring (engagement_status, coverage_office, decline fields, IM fee fields, etc.)
- [x] Multi-coverage junction table (person_coverage_owners)
- [x] Admin panel (fields, layouts, views, roles, users, reference data, duplicates)

### Blocking on IT
- [ ] SSO / Auth — Microsoft Entra ID app registration. Dev stub in `dependencies.py` (`get_current_user` returns hardcoded user). All routes use `Depends(get_current_user)` + `require_role()` — permissions enforced once SSO wired up.
- [ ] crm.aksia.com DNS
- [ ] Railway deployment config

### Blocking on Business Stakeholders
- [ ] Ostrako NDA export format — Ostrako/IT
- [ ] Authorized senders for publication lists — Marketing
- [ ] Declined reason codes for Fundraise Leads — Product
- [ ] Offshore feeder fund DL structure — Product/IR
- [ ] Soft Circle vs Hard Circle logic — Product
- [ ] Management dashboard access list — Leadership
- [ ] Audit log access beyond Admins — Leadership
- [ ] Events management spec — Aggeliki/Marketing
- [ ] CRM name — Leadership

### Deferred (not Phase 1)
- [ ] Multi-tenant architecture
- [ ] Generic admin-configurable calculated fields
- [ ] Duplicate detection merge UI
- [ ] Editable Excel-style grid

## Dev Workflow
```bash
cd echo2 && python -m uvicorn main:app --reload --port 8000
```
**Windows:** Always kill ALL python.exe processes before restarting (`taskkill /F /IM python.exe`). Windows allows multiple processes on the same port — a fresh uvicorn succeeding does NOT mean old servers are gone.

## Session History
Detailed session-by-session notes (28 sessions, March 11–27, 2026) are in `SESSION_LOG.md`. Consult for historical context on specific decisions. For current state, read the code.

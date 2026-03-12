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
- [ ] Organizations module (router logic)
- [ ] People module (router logic)
- [ ] Activities module (router logic)
- [ ] Leads module (router logic)
- [ ] Contracts module (router logic)
- [ ] Fund Prospects module (router logic)
- [ ] Distribution Lists module (router logic)
- [ ] Tasks module (router logic)
- [ ] Dashboards module (router logic)
- [ ] Admin module (router logic)
- [ ] Reference Data management
- [ ] SSO / Auth
- [ ] Data migration
- [ ] Dummy data test suite (10,000 rows)

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

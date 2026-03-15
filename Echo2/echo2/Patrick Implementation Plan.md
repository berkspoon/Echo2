# Echo 2.0 — Patrick Implementation Plan

## Context

Patrick (senior partner) and Miles reviewed the current prototype and approved 15 architectural changes. The core theme: move from hardcoded fields and views to a flexible, admin-configurable system using a hybrid EAV schema. This requires a substantial rebuild of the schema and codebase.

**Current state:** 20 tables, 10 routers, 64 templates. All forms/lists are hardcoded HTML. Single role per user. Fund Prospects is a separate module from Leads. Admin router is a stub.

**Target state:** Hybrid EAV with admin-configurable fields, merged fund prospects into leads, documents/attachments, multi-role permissions, reusable grid component, full admin panel.

**Process:** After completing each phase (starting from Phase 1 onward), STOP and wait for Miles to manually review and approve before proceeding to the next phase. Do not continue to the next phase without explicit approval.

---

## Phase 0: Extract Shared Utilities (Prerequisite) — DONE

Every router duplicates `_get_reference_data`, `_log_field_change`, `_audit_changes`, `_get_org_name`, `_get_user_name`. Extract these before touching 9 routers for EAV/role changes.

**Create:** `db/helpers.py`
- Move all duplicated helpers here with shared signatures
- `_audit_changes()` takes `record_type` param (contracts.py already does this; others hardcode it)

**Modify:** All 9 routers — replace local function definitions with imports from `db.helpers`

**Verify:** All existing page loads and form submissions still work.

---

## Phase 1: Schema Foundation (Changes 1, 4, 3, 6, 5) — DONE

> **CHECKPOINT:** After Phase 1 is complete, STOP and present results to Miles for manual review before proceeding to Phase 2.

### Step 1.1: `field_definitions` + `entity_custom_values` tables [Change 1]

**Schema** — Add to `db/schema.sql`:

`field_definitions` table:
- id, entity_type, field_name (UNIQUE per entity_type), display_name, field_type (text/number/date/boolean/dropdown/multi_select/lookup/address/phone/currency/calculated/url/email/textarea), storage_type (core_column/eav), is_required, is_system, display_order, section_name, validation_rules (JSONB), dropdown_category (references reference_data), dropdown_options (JSONB), calculation_expression, default_value, is_active, visibility_rules (JSONB), grid_default_visible, grid_sortable, grid_filterable

`entity_custom_values` table (EAV storage):
- id, entity_type, entity_id, field_definition_id (FK), value_text, value_number, value_date, value_boolean, value_json
- UNIQUE on (entity_type, entity_id, field_definition_id)

**Create:** `scripts/seed_field_definitions.py` — seed one row per existing column per entity. All as `storage_type='core_column'` initially. Encode existing conditional visibility (e.g., client questionnaire fields → `visibility_rules: {"when": "relationship_type", "equals": "client"}`; lead stage gating → `visibility_rules: {"min_stage": 2}`).

**Create:** `db/field_service.py` — `get_field_definitions(entity_type)`, `save_custom_values()`, `load_custom_values()`, `load_custom_values_batch()`.

**No router/template changes yet.** Existing code continues to work.

### Step 1.2: `roles` + `user_roles` tables [Change 4]

**Schema:**

`roles` table: id, role_name (unique), display_name, permissions (JSONB — `{entity: {action: bool}}`), is_system, is_active

`user_roles` junction: user_id (FK), role_id (FK), assigned_by, assigned_at, UNIQUE(user_id, role_id)

**Seed 6 roles:** Admin, Legal, RFP Team, BD, Standard, Read Only — with JSONB permissions.

**Data migration:** For each existing user, create a `user_roles` row mapping their current `role` column. Keep `role` column temporarily for backward compat.

**Modify:** `dependencies.py`
- `CurrentUser.__init__` takes `roles: list[str]` (plural); add backward-compat `role` property (returns first role)
- Add `has_permission(entity_type, action)` method aggregating across roles
- `get_current_user()` queries `user_roles` JOIN `roles`
- `require_role()` changes to `if not any(r in allowed_roles for r in user.roles)` — all 52 existing calls across 9 routers continue working unchanged

**Modify:** `base.html` — `{% if user.role == 'admin' %}` → `{% if 'admin' in user.roles %}`

### Step 1.3: `documents` table [Change 3]

**Schema:** id, title, file_url, file_type, file_size, entity_type, entity_id, uploaded_by (FK), uploaded_at, is_deleted

**Create:** `routers/documents.py` — HTMX endpoints for list/upload/delete/download per entity

**Create:** `templates/components/_tab_documents.html` — reusable document tab partial

**Modify:** Org, Person, Lead, Contract detail templates — add Documents tab

### Step 1.4: `lead_owners` junction table [Change 6]

**Schema:** lead_id (FK), user_id (FK), is_primary, UNIQUE(lead_id, user_id)

**Data migration:** For each lead with `aksia_owner_id`, insert a `lead_owners` row with `is_primary=true`. Keep `aksia_owner_id` column temporarily.

**Modify:** `routers/leads.py` — form parsing: multi-select `owner_ids[]`; create/update: sync `lead_owners`; list enrichment: batch query owners; validation: at least one required

**Modify:** Lead form template — replace single `<select>` with multi-select; Lead detail — show all owners; Lead list table — primary owner + "+N"

**Modify:** `routers/dashboards.py` — owner filters query `lead_owners` instead of `aksia_owner_id`

### Step 1.5: Person↔Org date tracking [Change 5]

**Schema:** Add `start_date DATE`, `end_date DATE` to `person_organization_links`

**Modify:** `routers/people.py` — set `start_date=today` on create; on primary org change: set `end_date=today` on old link, `start_date=today` on new

**Modify:** Org detail people tab — show dates; hide secondary orgs by default

---

## Phase 2: Merge Fund Prospects into Leads [Change 2] — DONE (Session 13, March 15, 2026)

> **CHECKPOINT:** After Phase 2 is complete, STOP and present results to Miles for manual review before proceeding to Phase 3.

**Depends on:** Phase 1 (Steps 1.1 and 1.4)

### Step 2.1: Alter leads table

Add columns: `lead_type` (advisory/product/fundraise, default 'advisory'), `fund_id` (FK → funds), `share_class`, `decline_reason`, `target_allocation_mn`, `soft_circle_mn`, `hard_circle_mn`, `probability_pct`, `stage_entry_date`

Add reference_data: `lead_type` category with 3 values; fund prospect stages merged into lead stages (use `parent_value` on `lead_stage` reference_data to scope stages by lead_type)

### Step 2.2: Data migration script

**Create:** `scripts/migrate_fund_prospects.py`
- For each fund_prospect row → create a lead with `lead_type='fundraise'`, mapped stage, copied allocation fields
- Update `tasks` where `linked_record_type='fund_prospect'` → `'lead'`
- Update `record_tags` similarly
- Keep fund_prospects table as backup (do not drop)

### Step 2.3: Codebase cleanup

**Delete:** `routers/fund_prospects.py`, `models/fund_prospect.py`, `templates/fund_prospects/` (all files)

**Modify:** `main.py` — remove fund_prospects router import

**Modify:** `templates/base.html` — remove "Fund Prospects" sidebar link

**Modify:** `routers/leads.py` — add `lead_type` handling:
- Form rendering: show fund/allocation fields when `lead_type` is 'fundraise' or 'product'; show advisory fields when 'advisory'
- Stage list: scope by lead_type
- Validation: fundraise requires fund_id, share_class; advisory requires service_type

**Modify:** `routers/dashboards.py`:
- Capital Raise dashboard: query `leads` WHERE `lead_type IN ('product', 'fundraise')`
- Management dashboard: update fundraising queries
- Personal dashboard: update coverage widgets

**Modify:** Organization detail — replace fund_prospects tab with fundraise leads tab

**Modify:** `routers/tasks.py` — remove `fund_prospect` from linked_record_type options

**Modify:** `scripts/seed_data.py` — seed fundraise leads instead of fund_prospects

### Step 2.4: Seed field_definitions for new fundraise lead fields

---

## Phase 3: Admin Control Panel [Changes 10.1, 10.2, 10.3] — DONE (Session 14, March 15, 2026)

> **CHECKPOINT:** After Phase 3 is complete, STOP and present results to Miles for manual review before proceeding to Phase 4.
> **STATUS:** Completed. All 4 steps implemented, 11 Python files + 10 templates verified.

### Step 3.1: Field Management [Change 10.1]

**Modify:** `routers/admin.py` (currently a stub) — add CRUD for field_definitions:
- List fields by entity_type, create/edit field, reorder, deactivate
- System fields (is_system=true) cannot be deleted

**Create:** `templates/admin/fields.html`, `templates/admin/field_form.html`, `templates/admin/_field_list_partial.html`

### Step 3.2: Dynamic Form Rendering [Change 1 continued]

This is the centerpiece. Transition forms from hardcoded HTML to metadata-driven rendering.

**Create:** `services/form_service.py`
- `build_form_context(entity_type, record=None)` — loads field_defs, groups by section, loads dropdown options
- `parse_form_data(entity_type, form_data, field_defs)` — replaces hardcoded `_build_*_data_from_form()` in each router
- `validate_form_data(entity_type, data, field_defs)` — replaces hardcoded validation
- `save_record(entity_type, data, field_defs, record_id=None)` — splits core vs EAV, writes both, handles audit

**Create:** `templates/components/_field_renderer.html` — Jinja2 macro rendering one field by field_type (text input, select, multi-select checkboxes, textarea, date, boolean, currency, url, email, lookup/autocomplete)

**Create:** `templates/components/_form_section.html` — Jinja2 macro rendering a section (loops over fields, calls `_field_renderer`)

**Migration order** (simplest → most complex):
1. Tasks (6 fields, no conditional visibility)
2. Activities (multi-select lookups for orgs/people)
3. Contracts (Legal-only restrictions)
4. People (org autocomplete, DNC logic)
5. Organizations (conditional client questionnaire, RFP hold)
6. Leads (stage-gated visibility, multiple lead_types, conditional fields) — most complex

For each entity: update router to use form_service, replace hardcoded form.html with dynamic macros, keep entity-specific JS (make it data-driven from visibility_rules), test full CRUD flow.

### Step 3.3: Page Layout Designer [Change 10.2]

**Schema:** `page_layouts` table — entity_type, layout_type (view/edit), sections (JSONB), is_active

**Modify:** `routers/admin.py` — layout CRUD endpoints

**Create:** `templates/admin/layout_designer.html`

### Step 3.4: Role Management + User Management [Change 10.3]

**Modify:** `routers/admin.py` — role CRUD, user↔role assignment, user deactivation

**Create:** `templates/admin/roles.html`, `templates/admin/role_form.html`

**Modify:** `templates/admin/users.html` — add role assignment multi-select

---

## Phase 4: Reusable Grid Component [Change 8] — DONE (Session 15, March 15, 2026)

**Depends on:** Phase 3 Step 3.2 (field_definitions must be consumed by forms first)
> **STATUS:** Completed. Grid service (~600 lines), grid template (~400 lines), column selector, saved views router. All 7 entity list pages migrated. 8 old `_list_table.html` partials deleted.

### Step 4.1: Grid component

**Create:** `templates/components/_grid.html` — single Jinja2 template accepting columns (from field_defs), rows, pagination, sort, filters

Features: sortable headers, per-column filters (type-aware: text search, dropdown, date range), column show/hide panel, HTMX-driven pagination/sort/filter

**Create:** `templates/components/_column_selector.html` — dropdown panel listing all fields for entity, checkboxes toggle visibility

### Step 4.2: Saved Views

**Schema:** `saved_views` table — user_id, entity_type, view_name, columns (JSONB), filters (JSONB), sort_by, sort_dir, is_default, is_shared

**Create:** `services/grid_service.py`
- `build_grid_context(entity_type, request, user, saved_view_id=None)` — loads field_defs, applies view config, queries data, enriches rows
- Saved view CRUD endpoints

### Step 4.3: Deploy grid on all entities

**Modify:** All entity list routes — replace custom list logic with `grid_service.build_grid_context()`. Each list handler shrinks from ~60-80 lines to ~15.

**Delete:** All 8 `_list_table.html` partials (replaced by `_grid.html`)

**Modify:** All 8 `list.html` templates — include `_grid.html` instead of entity-specific partial

---

## Phase 5: Remaining Changes [Changes 9, 11, 12, 13, 14, 15] — DONE (Session 16, March 15, 2026)

> **CHECKPOINT:** After Phase 4 is complete, STOP and present results to Miles for manual review before proceeding to Phase 5.
> **STATUS:** Completed. All 6 steps (5.0–5.6) implemented. Reference Data CRUD, Lead Finder virtual columns, manual contract creation, DL bulk add + people DL tab + follow-up assignee, soft delete rename, duplicate detection enhancements (suppression + admin batch scan). Merge endpoint deferred as stretch goal.

### Step 5.1: Lead Finder Saved View [Change 11]

**Modify:** `services/grid_service.py` — support virtual columns (e.g., "Active Leads" = count of active leads per org)

**Seed:** Default shared saved view "Lead Finder" on org grid with active_leads_count column

HTMX inline lead display when clicking active leads count; inline stage/rating editing

### Step 5.2: Lead→Contract Manual Creation [Change 9]

**Modify:** `routers/leads.py` — remove auto-contract-creation when stage=Won

**Modify:** `routers/contracts.py` — add `GET /contracts/new?lead_id=X` (Legal/Admin only) and `POST /contracts`

**Modify:** Lead detail template — "Create Contract" button visible to Legal/Admin when stage=Won and no contract exists

### Step 5.3: Distribution List Improvements [Change 12]

**Modify:** `routers/people.py` — add DL membership tab to person detail
**Create:** `templates/people/_tab_distribution_lists.html`
**Modify:** `routers/distribution_lists.py` — add "Add All" bulk endpoint for filtered results

### Step 5.4: Follow-Up Task Assignment [Change 13]

**Modify:** `routers/activities.py` — follow-up task assignee becomes a form dropdown (coverage team members), defaulting to activity author

**Modify:** Activities form template — add "Assign To" dropdown in follow-up section

### Step 5.5: Soft Delete Rename [Change 14]

**Schema:** Rename `is_archived` → `is_deleted` on all entity tables (12 ALTER TABLE statements)

**Modify:** All 9 routers + templates — global replace `is_archived` → `is_deleted`

Note: `distribution_lists.is_active` stays as-is (it's a status field, not soft-delete)

**Add:** Admin restore endpoint: `POST /admin/{entity_type}/{id}/restore`

### Step 5.6: Duplicate Detection Enhancements [Change 15]

**Schema:** `duplicate_suppressions` table — entity_type, record_id_a, record_id_b, suppressed_by, UNIQUE on (entity_type, record_id_a, record_id_b)

**Modify:** Org/people routers — filter out suppressed pairs from duplicate results; store suppression when user confirms "Not a Duplicate"

**Add:** Admin batch scan: `GET /admin/duplicates/{entity_type}` — full-table similarity scan with merge UI

> **CHECKPOINT:** After Phase 5 is complete, STOP and present results to Miles for final review. All 15 changes are now implemented.
> **STATUS:** Complete. All 15 architectural changes from the Patrick Implementation Plan are now implemented across Phases 0–5.

---

## Key Files to Modify

| File | Changes |
|------|---------|
| `db/schema.sql` | 7 new tables, 3 altered tables |
| `dependencies.py` | Multi-role auth |
| `routers/leads.py` | Fund prospect merge, lead_type, multi-owner, dynamic forms |
| `routers/admin.py` | Full admin panel (currently a stub) |
| `routers/dashboards.py` | Capital raise queries, fund prospect references |
| `main.py` | Remove fund_prospects router, add documents router |
| `templates/base.html` | Sidebar nav updates, role checks |
| All 8 entity form templates | Replace with dynamic rendering |
| All 8 entity list table partials | Replace with reusable grid |

## New Files to Create

| File | Purpose |
|------|---------|
| `db/helpers.py` | Shared audit/reference helpers |
| `db/field_service.py` | Field definitions query/save |
| `services/form_service.py` | Dynamic form build/parse/validate/save |
| `services/grid_service.py` | Reusable grid data loading |
| `routers/documents.py` | Document upload/list/delete |
| `templates/components/_field_renderer.html` | Field rendering macro |
| `templates/components/_form_section.html` | Section rendering macro |
| `templates/components/_grid.html` | Reusable grid component |
| `templates/components/_column_selector.html` | Column show/hide panel |
| `templates/components/_tab_documents.html` | Document tab partial |
| `templates/admin/fields.html` | Field management |
| `templates/admin/field_form.html` | Field create/edit form |
| `templates/admin/roles.html` | Role management |
| `templates/admin/role_form.html` | Role create/edit form |
| `templates/admin/layout_designer.html` | Page layout designer |
| `scripts/seed_field_definitions.py` | Seed field_definitions table |
| `scripts/migrate_fund_prospects.py` | Migrate fund prospects to leads |

## Verification Plan

After each phase:
1. Run `python -m uvicorn main:app --reload --port 8000`
2. Verify all list views load correctly with data
3. Verify create/edit forms render and submit
4. Verify detail pages display correctly
5. Verify HTMX interactions (autocomplete, filters, tabs)
6. Verify role-based access restrictions
7. Run seed script to verify data integrity

After Phase 2 specifically:
- Verify all former fund prospect data appears as leads with type 'fundraise'
- Verify Capital Raise dashboard shows equivalent data
- Verify tasks previously linked to fund_prospects now link to leads

After Phase 3:
- Create a custom field via admin panel, verify it appears on forms and is saved/loaded correctly via EAV

After Phase 4:
- Verify column selector works, saved views persist, filters apply correctly

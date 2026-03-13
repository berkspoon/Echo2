# Admin Module — Build Prompt

**Build the Admin module for Echo 2.0.** This is the last functional module on the checklist (see CLAUDE.md "What Has Been Built So Far"). The module provides admin-only tools for managing users, reference data, audit logs, data quality, duplicate merging, and tags.

Read the PRD first — it is the source of truth:
- `Echo_2.0_PRD - Final.docx` — **Section 11 (Admin & Data Quality)**: subsections 11.1 (User Management), 11.2 (Data Quality Alerts), 11.3 (Duplicate Management), 11.4 (Audit Log), 11.6 (Reference Data Management), 11.6.3 (Tags). Also Table 1 (User Roles & Permissions), Table 24 (Data Quality Alerts), Table 25 (Reference Data Categories). Use `python-docx` to extract the content if needed. If there's any conflict between this prompt and the PRD, the PRD wins.

Then read these files — they contain the codebase patterns you must follow:
- `routers/dashboards.py` (batch resolution helpers, admin-gated route pattern with `require_role`)
- `routers/organizations.py` (duplicate detection with `check_org_name_similarity()`, audit logging pattern `_audit_changes()`, HTMX partials)
- `routers/people.py` (duplicate detection with `check_person_name_similarity()`, DNC enforcement, person-org links)
- `routers/leads.py` (filter form HTMX pattern, reference_data loading, pagination)
- `templates/leads/list.html` (HTMX filter form wiring — `hx-get`, `hx-target`, `hx-push-url`)
- `templates/base.html` (sidebar structure — note the Admin section links)
- `models/user.py` (existing UserCreate/UserUpdate/UserResponse Pydantic models)
- `dependencies.py` (get_current_user dev stub, require_role helper, CurrentUser class)
- `db/schema.sql` (reference_data table, users table, audit_log table, tags table, record_tags table)

---

## What to build (6 features, ~12 routes, ~10 templates)

**Every route in this module must be admin-only:** `require_role(current_user, ["admin"])`.

---

### 1. User Management (`GET /admin/users`)

List all users with ability to edit roles and activate/deactivate.

**Routes:**

| Method | Path | Description |
|--------|------|-------------|
| `GET /admin/users` | List all users (active + inactive) with search/filter |
| `GET /admin/users/{user_id}/edit` | Edit form (HTMX partial) |
| `POST /admin/users/{user_id}/update` | Update user role, active status |
| `POST /admin/users/{user_id}/deactivate` | Deactivate a user (set `is_active=False`) |
| `POST /admin/users/{user_id}/reactivate` | Reactivate a deactivated user |

**List page:** Table with columns: Name, Email, Role (badge), Status (active/inactive badge), Last Login, Actions (Edit/Deactivate buttons). Search by name/email. Filter by role and active status.

**Edit:** Inline HTMX form (like fee arrangements on org detail page). Only editable fields: `role` (dropdown: admin, legal, rfp_team, standard_user, read_only), `display_name`, `is_active`. Cannot edit own role (prevent admin self-demotion). Cannot deactivate self.

**Deactivation behavior (PRD 11.1):**
- Set `is_active = False`
- Create a system Task assigned to an admin: "Reassign open leads and uncovered contacts for [display_name]"
- Log the role change to audit_log

**Role badges:** admin=red, legal=purple, rfp_team=blue, standard_user=gray, read_only=yellow.
**Status badges:** active=green, inactive=red.

**Templates:**
- `templates/admin/users.html` — rewrite existing stub (full page with table)
- `templates/admin/_users_table.html` — new partial (HTMX table swap)
- `templates/admin/_user_edit_form.html` — new partial (inline edit form)

---

### 2. Reference Data Management (`GET /admin/reference-data`)

CRUD for all reference_data categories. This is the **Settings > Reference Data** UI from PRD 11.6.

**Routes:**

| Method | Path | Description |
|--------|------|-------------|
| `GET /admin/reference-data` | Category list (sidebar) + values table |
| `GET /admin/reference-data/{category}` | Values for a specific category |
| `POST /admin/reference-data/{category}/add` | Add a new value |
| `POST /admin/reference-data/{category}/{value_id}/update` | Update label, display_order, is_active |
| `POST /admin/reference-data/{category}/{value_id}/deactivate` | Soft-deactivate (set `is_active=False`) |
| `POST /admin/reference-data/{category}/{value_id}/reactivate` | Reactivate |

**Layout:** Two-panel: left sidebar lists all categories (clickable), right panel shows values for the selected category. When a category is clicked, use HTMX to swap the right panel content.

**Category list:** Query `SELECT DISTINCT category FROM reference_data ORDER BY category`. Display as readable labels (e.g., `organization_type` → "Organization Type"). Include count of active values per category.

**Values table:** For the selected category, show all values (active + inactive) sorted by `display_order`. Columns: Value, Label, Display Order, Status (active/inactive), Parent Value (if applicable, e.g., activity subtypes), Actions.

**Add form:** Inline form at top of values table (HTMX). Fields: value (slug), label (display text), display_order (integer), parent_value (optional — show only for categories that use it like `activity_subtype`).

**Edit:** Inline HTMX form replacing the row. Editable: label, display_order, is_active. The `value` field is read-only after creation (changing it could break existing records).

**Deactivation (PRD 11.6.2):** Deactivating a value hides it from new record dropdowns but preserves it on existing records. Show deactivated values in the table with a muted/strikethrough style and a "Reactivate" button.

**Important:** The `value` column is the internal key used in database records. The `label` column is the display text shown in dropdowns. Both are stored. Renaming a `label` updates it everywhere it appears. Never change `value` after creation.

**Templates:**
- `templates/admin/reference_data.html` — rewrite existing stub
- `templates/admin/_reference_values.html` — new partial (values table for selected category)
- `templates/admin/_reference_value_form.html` — new partial (inline add/edit form)

---

### 3. Audit Log Viewer (`GET /admin/audit-log`)

Global view of all field-level changes across the system. This is the global Admin view from PRD 11.4.

**Routes:**

| Method | Path | Description |
|--------|------|-------------|
| `GET /admin/audit-log` | Filterable, paginated audit log |

**Filters (HTMX filter form, same pattern as leads list):**
- Record Type (dropdown: organization, person, activity, lead, contract, fund_prospect, distribution_list, task, fee_arrangement)
- User (dropdown of all users)
- Date Range (from/to on `changed_at`)
- Field Name (text input — search/filter by field)
- Record ID (text input — search specific record)

**Table columns:** Timestamp (formatted), Record Type (badge), Record ID (linked to detail page if possible), Field, Old Value, New Value, Changed By (user name).

**Pagination:** 50 rows per page. Use the same offset/limit pagination pattern as other list pages.

**Batch resolve** user names for `changed_by` column.

**Record links:** For each audit entry, generate a link to the record's detail page based on `record_type` and `record_id` (e.g., `/organizations/{id}`, `/leads/{id}`, etc.).

**Templates:**
- `templates/admin/audit_log.html` — new (full page)
- `templates/admin/_audit_log_table.html` — new partial (HTMX table swap)

---

### 4. Data Quality Alerts (`GET /admin/data-quality`)

Run automated checks and display results per PRD 11.2 / Table 24.

**Routes:**

| Method | Path | Description |
|--------|------|-------------|
| `GET /admin/data-quality` | Data quality dashboard |
| `POST /admin/data-quality/run` | Trigger on-demand check (HTMX) |

**5 alert checks (from PRD Table 24):**

1. **Leads without owners** — Active leads where `aksia_owner_id IS NULL` or owner is inactive user. Show count + expandable list with lead summary, org name, link to lead.

2. **Contacts without coverage** — People who are members of at least one active distribution list but have `coverage_owner_id IS NULL`. Show count + list with name, org, link.

3. **Contacts with invalid emails** — People where `email IS NULL` or email doesn't match basic format (`@` and `.`). Show count + list with name, org, link.

4. **Orgs with no activity in 12 months** — Organizations with no linked activities (via `activity_organization_links`) where `effective_date` is within the last 12 months. Show count + list with org name, last activity date, link.

5. **Expired NDAs** — Organizations where `nda_expiration_date` is within 30 days of today or has passed. Show count + list with org name, expiration date, link. (Note: NDA fields may not be populated in seed data — handle gracefully with "No NDA data available" empty state.)

**Layout:** Card grid showing each alert type with count (color-coded: red if >0, green if 0). Each card is expandable to show the full list. "Run Checks" button at top triggers a full refresh via HTMX.

**Templates:**
- `templates/admin/data_quality.html` — new (full page)
- `templates/admin/_data_quality_results.html` — new partial (HTMX swap on run)

---

### 5. Duplicate Merge Tools (`GET /admin/merge/organizations` and `/admin/merge/people`)

Admin merge tools per PRD 11.3.

**Routes:**

| Method | Path | Description |
|--------|------|-------------|
| `GET /admin/merge/organizations` | Org merge tool page |
| `POST /admin/merge/organizations/search` | HTMX: search for orgs to merge |
| `POST /admin/merge/organizations/preview` | HTMX: preview merge (show what will move) |
| `POST /admin/merge/organizations/execute` | Execute the merge |
| `GET /admin/merge/people` | Person merge tool page |
| `POST /admin/merge/people/search` | HTMX: search for people to merge |
| `POST /admin/merge/people/preview` | HTMX: preview merge |
| `POST /admin/merge/people/execute` | Execute the merge |

**Organization Merge (PRD 11.3):**
- Two-step: select two orgs → preview → confirm merge
- Search uses existing `check_org_name_similarity()` PostgreSQL function, or standard ILIKE search
- Preview shows: surviving org (user picks which), records that will be moved (people links, activities, leads, fund_prospects, contracts, fee_arrangements, tags)
- Execute: move all linked records to surviving org's ID, archive the merged org (`is_archived=True`), log all moves to audit_log
- Tables to update: `person_organization_links`, `activity_organization_links`, `leads` (organization_id), `fund_prospects` (organization_id), `contracts` (organization_id), `fee_arrangements` (organization_id), `record_tags` (where record_type='organization')

**Person Merge:**
- Same two-step flow: select two people → preview → confirm
- Preview shows: surviving person, records to move (activities links, distribution list memberships, tasks, tags)
- Execute: move all linked records, merge org links (deduplicate — if both people are linked to same org, keep surviving person's link), archive merged person
- Tables to update: `activity_people_links`, `distribution_list_members`, `tasks` (where linked_record_type='person'), `person_organization_links`, `record_tags` (where record_type='person')

**Important merge rules:**
- The merged (non-surviving) record is archived, never hard-deleted
- Every record move is logged to `audit_log`
- Handle duplicate junction table entries gracefully (e.g., both people linked to the same activity — don't create a duplicate link, just archive the duplicate person's link)

**Templates:**
- `templates/admin/merge_organizations.html` — new
- `templates/admin/merge_people.html` — new
- `templates/admin/_merge_preview.html` — new partial (shared for both org and person merge previews)

---

### 6. Tag Management (`GET /admin/tags`)

View, rename, merge, and delete tags per PRD 11.6.3.

**Routes:**

| Method | Path | Description |
|--------|------|-------------|
| `GET /admin/tags` | List all tags with usage counts |
| `POST /admin/tags/{tag_id}/rename` | Rename a tag |
| `POST /admin/tags/{tag_id}/delete` | Delete tag (remove from all records) |
| `POST /admin/tags/merge` | Merge two tags (move all record_tags to surviving tag, delete merged tag) |

**List page:** Table with columns: Tag Name, Usage Count (number of record_tags), Created By, Created At, Actions (Rename, Delete, Merge). Search by tag name.

**Usage count:** `SELECT tag_id, COUNT(*) FROM record_tags GROUP BY tag_id`

**Rename:** Inline HTMX edit on the tag name.

**Delete:** Confirmation dialog. Deletes the tag from `tags` table (CASCADE deletes from `record_tags`).

**Merge:** Select two tags, pick surviving name, move all `record_tags` from merged tag to surviving tag (handle duplicates — same record can't have same tag twice), then delete merged tag.

**Templates:**
- `templates/admin/tags.html` — new

---

## Sidebar Update

The Admin section in `base.html` sidebar currently shows User Management and Reference Data links to ALL users. **Wrap the entire Admin section** (header + all links) in `{% if user is defined and user.role == 'admin' %}`. Add these additional links:
- Audit Log (`/admin/audit-log`) — book icon
- Data Quality (`/admin/data-quality`) — exclamation-triangle icon
- Merge Tools (`/admin/merge/organizations`) — "Merge" with arrows icon
- Tags (`/admin/tags`) — tag icon

---

## Implementation order

Build in this sequence — each step establishes patterns reused by the next:

1. **Reference Data Management** — foundational, establishes the inline HTMX CRUD pattern
2. **User Management** — builds on CRUD pattern, adds deactivation logic
3. **Audit Log Viewer** — read-only with filters, straightforward
4. **Data Quality Alerts** — read-only aggregation queries
5. **Tag Management** — small CRUD + merge
6. **Duplicate Merge Tools** — most complex, do last

## Coding rules (from CLAUDE.md — follow exactly)

- `require_role(current_user, ["admin"])` on **every** route in this module
- `current_user: CurrentUser = Depends(get_current_user)` on every route
- All queries via `get_supabase_client()` from `db/client.py`
- Filter `is_archived = False` on entity queries (but NOT on reference_data — show inactive values too, marked differently)
- Check `request.headers.get("HX-Request")` for HTMX partial vs full page
- Templates extend `base.html`, partials do NOT extend anything
- Dropdown labels from `reference_data` table, never hardcoded
- Empty states for every section
- Currency: `'{:,.0f}'.format(value)` — commas, no decimals
- Audit log every change: record_type, record_id, field_name, old_value, new_value, changed_by, changed_at
- Replicate helper functions inside the admin router — don't import from other routers
- Route ordering: static paths before `{param}` paths to avoid UUID parse conflicts

## Verification

After building, test by running `python -m uvicorn main:app --reload --port 8000` and checking:
1. User Management (`/admin/users`) — table loads, role edit works, deactivation creates reassignment task
2. Reference Data (`/admin/reference-data`) — categories list, values table, add/edit/deactivate work
3. Audit Log (`/admin/audit-log`) — entries display, filters work (HTMX partial swap)
4. Data Quality (`/admin/data-quality`) — all 5 checks run, counts display, expandable lists work
5. Merge Orgs (`/admin/merge/organizations`) — search, preview, execute work (verify linked records moved)
6. Merge People (`/admin/merge/people`) — same
7. Tags (`/admin/tags`) — list with counts, rename, delete, merge work
8. All sidebar links work, admin section only visible to admin role
9. Non-admin user gets 403 on all `/admin/*` routes

---

## Key files to read before starting

| File | Why |
|------|-----|
| `Echo_2.0_PRD - Final.docx` | **READ FIRST.** Section 11 (Admin & Data Quality) is the source of truth. |
| `routers/organizations.py` | `_audit_changes()` pattern, `check_org_name_similarity()` usage, HTMX partials |
| `routers/people.py` | `check_person_name_similarity()` usage, person-org links management |
| `routers/leads.py` | Filter form pattern, pagination, reference_data loading |
| `routers/dashboards.py` | `require_role` usage, batch resolution helpers |
| `templates/leads/list.html` | HTMX filter form wiring |
| `templates/base.html` | Sidebar structure for adding admin links |
| `models/user.py` | Existing Pydantic models |
| `dependencies.py` | `get_current_user`, `require_role`, `CurrentUser` class |
| `db/schema.sql` | reference_data, users, audit_log, tags, record_tags table definitions |

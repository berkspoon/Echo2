# Phase 5: Remaining Changes + Reference Data Management

Execute **Phase 5** from `Echo2/echo2/Patrick Implementation Plan.md` — **Changes 9, 11, 12, 13, 14, 15** plus **Reference Data Admin CRUD**. Read `Echo2/CLAUDE.md` for coding standards and project context.

**Depends on:** Phases 0–4 are complete.

---

## Step 5.0: Reference Data Admin CRUD

The `reference_data` table already exists (17 seeded categories), `get_reference_data()` in `db/helpers.py` handles reads, and the sidebar link + stub endpoint in `routers/admin.py` exist. Build a full admin CRUD interface.

### Current state

- **Table schema** (`db/schema.sql`):
  ```sql
  CREATE TABLE reference_data (
      id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
      category        TEXT NOT NULL,
      value           TEXT NOT NULL,
      label           TEXT NOT NULL,
      parent_value    TEXT,
      display_order   INT NOT NULL DEFAULT 0,
      is_active       BOOLEAN NOT NULL DEFAULT TRUE,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE(category, value)
  );
  ```
- **17 seeded categories:** organization_type, relationship_type, country, activity_type, activity_subtype, lead_stage, lead_relationship_type, service_type, asset_class, pricing_proposal, rfp_status, risk_weight, lead_type, decline_reason, document_type, publication_list, fund (in funds table, not reference_data — skip this one)
- **Hierarchical data:** `activity_subtype` has `parent_value` scoping to parent activity type; `lead_stage` has `parent_value` scoping to lead_type ('advisory'/'fundraise')
- **Stub endpoint:** `GET /admin/reference-data` in `routers/admin.py` (line ~841) returns empty template
- **Stub template:** `templates/admin/reference_data.html` shows "Loading..."

### Endpoints to add in `routers/admin.py`

All endpoints require `require_role(current_user, ["admin"])`.

| Method | Path | Purpose | Response |
|--------|------|---------|----------|
| `GET` | `/admin/reference-data` | Category browser — list all categories with value counts | Full page (`reference_data.html`) |
| `GET` | `/admin/reference-data/{category}` | Values list for a category | HTMX partial (`_reference_data_values.html`) targeting `#rd-values-panel` |
| `GET` | `/admin/reference-data/{category}/new` | New value form | HTMX partial (`_reference_data_form.html`) targeting `#rd-form-panel` |
| `POST` | `/admin/reference-data/{category}` | Create value | HTMX swap back to values list |
| `GET` | `/admin/reference-data/{category}/{rd_id}/edit` | Edit value form | HTMX partial (`_reference_data_form.html`) targeting `#rd-form-panel` |
| `POST` | `/admin/reference-data/{category}/{rd_id}` | Update value | HTMX swap back to values list |
| `POST` | `/admin/reference-data/{category}/{rd_id}/toggle` | Toggle is_active | HTMX swap values list (inline) |
| `POST` | `/admin/reference-data/{category}/{rd_id}/reorder` | Move up/down | HTMX swap values list |

### Create endpoint: validation rules
- `value` is required, must be `[a-z0-9_]` (snake_case slug), unique within category
- `label` is required (display text)
- `parent_value` — required for `activity_subtype` and `lead_stage` categories; must be a valid value in the logical parent category (activity_type or lead_type respectively)
- `display_order` defaults to max+1 in category

### Update endpoint: restrictions
- `value` cannot be changed after creation (it's referenced by other tables)
- `category` cannot be changed
- `label`, `display_order`, `parent_value`, `is_active` can be changed
- Audit log all changes via `audit_changes()` helper with `record_type="reference_data"`

### Toggle endpoint: safety check
- Before deactivating, check if the value is currently in use. Query the relevant entity table(s) to see if any records reference this value. If in use, warn but still allow deactivation (values may need to be hidden from future forms while preserving existing data).

### Reorder endpoint
- Accept `direction` param (`up` or `down`)
- Swap `display_order` with the adjacent item in the same category (and same `parent_value` if hierarchical)

### Templates to create

**`templates/admin/reference_data.html`** — rewrite the stub. Layout:
- Left panel: category list with count badges, click loads values via HTMX into right panel
- Right panel (`#rd-values-panel`): values table for selected category
- Form panel (`#rd-form-panel`): inline create/edit form (appears above or replaces values table)
- Use a two-column layout: `grid grid-cols-4` (1 col sidebar, 3 col content)
- Category sidebar: list of categories as clickable items, each with `hx-get="/admin/reference-data/{category}" hx-target="#rd-values-panel"`
- Highlight active category

**`templates/admin/_reference_data_values.html`** — HTMX partial for the values table:
- Table columns: Display Order, Value (code), Label, Parent Value (if applicable), Status (active/inactive badge), Actions (Edit, Toggle, Move Up/Down)
- "Add New Value" button at top
- Group by `parent_value` for hierarchical categories (show parent as section header)
- Inactive values shown with muted styling and "Inactive" badge

**`templates/admin/_reference_data_form.html`** — HTMX partial for create/edit:
- Fields: Value (text input, read-only on edit), Label (text input), Parent Value (dropdown, shown only for hierarchical categories), Display Order (number), Is Active (checkbox)
- Parent Value dropdown: for `activity_subtype`, show activity_type values; for `lead_stage`, show lead_type values
- Save and Cancel buttons
- Validation error display

### Category metadata

Define a dict in the router or a constant for category display info:

```python
_CATEGORY_META = {
    "organization_type": {"label": "Organization Type", "parent_category": None},
    "relationship_type": {"label": "Relationship Type", "parent_category": None},
    "country": {"label": "Country", "parent_category": None},
    "activity_type": {"label": "Activity Type", "parent_category": None},
    "activity_subtype": {"label": "Activity Subtype", "parent_category": "activity_type"},
    "lead_stage": {"label": "Lead Stage", "parent_category": "lead_type"},
    "lead_relationship_type": {"label": "Lead Relationship Type", "parent_category": None},
    "service_type": {"label": "Service Type", "parent_category": None},
    "asset_class": {"label": "Asset Class", "parent_category": None},
    "pricing_proposal": {"label": "Pricing Proposal", "parent_category": None},
    "rfp_status": {"label": "RFP Status", "parent_category": None},
    "risk_weight": {"label": "Risk Weight", "parent_category": None},
    "lead_type": {"label": "Lead Type", "parent_category": None},
    "decline_reason": {"label": "Decline Reason", "parent_category": None},
    "document_type": {"label": "Document Type", "parent_category": None},
    "publication_list": {"label": "Publication List", "parent_category": None},
}
```

---

## Step 5.1: Lead Finder Saved View [Change 11]

### Modify: `services/grid_service.py`

Add support for **virtual/computed columns** — columns not backed by a real database field but computed from related data.

1. Add a `_VIRTUAL_COLUMNS` dict keyed by entity_type, each entry being a list of column definitions:
   ```python
   _VIRTUAL_COLUMNS = {
       "organization": [
           {
               "field_name": "active_leads_count",
               "display_name": "Active Leads",
               "field_type": "number",
               "sortable": False,
               "filterable": False,
               "section_name": "Computed",
           },
       ],
   }
   ```

2. In `_enrich_organizations()`, after the existing enrichment, add a batch query to count active leads per org:
   - Query `leads` table: `SELECT organization_id, COUNT(*) FROM leads WHERE is_archived=FALSE AND rating NOT IN ('won', 'lost') GROUP BY organization_id`
   - Attach `active_leads_count` to each org row

3. In `_resolve_visible_columns()`, merge virtual columns into the available columns list so they appear in the column selector.

### Seed: Default "Lead Finder" saved view

Add a seed SQL statement (or a note in schema.sql) for a shared saved view:
- `entity_type = 'organization'`
- `view_name = 'Lead Finder'`
- `is_shared = TRUE`
- `columns` includes: company_name, organization_type, hq_location, active_leads_count, relationship_type
- `sort_by = 'active_leads_count'`, `sort_dir = 'desc'`

### Modify: `templates/components/_grid.html`

Add cell rendering for `active_leads_count`:
- Display as a clickable number badge
- On click, expand an inline HTMX panel below the row showing the org's active leads (mini-table with lead summary, stage badge, owner)
- Use `hx-get="/organizations/{org_id}/leads-panel" hx-target="#leads-panel-{org_id}" hx-swap="innerHTML"`

### Add endpoint: `GET /organizations/{org_id}/leads-panel`

In `routers/organizations.py`:
- Query active leads for the org (not archived, not won/lost)
- Return an HTMX partial (`_org_leads_panel.html`) with a mini-table: Summary, Stage (badge), Service Type, Owner, Expected Revenue
- Include inline stage/rating editing via HTMX dropdowns (admin/standard_user only)

### Create: `templates/organizations/_org_leads_panel.html`

Mini-table partial showing active leads for an org. Each row has:
- Lead summary (linked to detail page)
- Stage badge (color-coded)
- Inline stage dropdown (HTMX `hx-post` to update stage)
- Owner name
- Expected revenue (formatted currency)

---

## Step 5.2: Lead→Contract Manual Creation [Change 9]

Currently, contracts are auto-created when a lead's rating changes to "won". Change this to a manual "Create Contract" action.

### Modify: `routers/leads.py`

- **Remove** the auto-contract-creation logic from `update_lead()`. When a lead is promoted to Won status, it should just update the lead's rating/stage and set end_date — do NOT auto-create a contract.
- Keep the existing audit logging for the stage change.

### Modify: `routers/contracts.py`

Add two new endpoints:

**`GET /contracts/new`** — Contract creation form
- Requires `require_role(current_user, ["admin", "legal"])`
- Accepts `?lead_id=<uuid>` query param (required)
- Load the lead and its organization
- Pre-fill contract fields from the lead: `organization_id`, `service_type`, `asset_classes`, `actual_revenue` (from lead's `expected_revenue`), `client_coverage` (from lead's `potential_coverage`)
- Render `contracts/form.html` (new template or modify existing edit form to handle create mode)

**`POST /contracts`** — Create contract
- Requires `require_role(current_user, ["admin", "legal"])`
- Validate: lead_id must exist, lead must be in Won stage, no existing contract for this lead
- Create contract record with `originating_lead_id = lead_id`, `start_date = today`
- Audit log the creation
- Redirect to contract detail page

### Modify: Lead detail template (`templates/leads/detail.html`)

- When lead stage is Won (rating = "won"/"inactive_won") AND no contract exists yet:
  - Show a "Create Contract" button (visible to admin + legal only)
  - Button links to `/contracts/new?lead_id={lead.id}`
- When a contract already exists:
  - Show "View Contract" link (existing behavior)

### Modify: Contract form template

- Ensure the form works for both create and edit modes
- On create: show lead info as read-only context at top, pre-filled fields
- On edit: existing behavior unchanged (Legal-only)

---

## Step 5.3: Distribution List Improvements [Change 12]

### Add: Person detail — Distribution List membership tab

**Modify: `routers/people.py`**
- In the `get_person()` detail endpoint, add a query to load all distribution list memberships for this person:
  ```python
  dl_resp = sb.table("distribution_list_members") \
      .select("distribution_list_id, added_at") \
      .eq("person_id", str(person_id)) \
      .eq("is_active", True) \
      .execute()
  ```
- Batch-resolve distribution list names from `distribution_lists` table
- Pass `memberships` list to the template context

**Create: `templates/people/_tab_distribution_lists.html`**
- Table showing: List Name (linked), Type badge, Brand badge, Member Since (date)
- "Remove" button per row (HTMX POST to remove membership, admin/standard_user only)
- If person has DNC enabled, show warning banner: "This person has Do Not Contact enabled — they cannot be added to distribution lists"

**Modify: `templates/people/detail.html`**
- Add a "Distribution Lists" tab alongside existing tabs (Activities, Organizations, etc.)
- Tab loads `_tab_distribution_lists.html`

### Add: Bulk "Add All" to distribution list

**Modify: `routers/distribution_lists.py`**

Add endpoint: `POST /distribution-lists/{list_id}/add-filtered`
- Accepts a JSON body or form data with filter criteria matching the member search filters (country, rel_type, fund)
- Executes the same filtered person query as the search endpoint
- For each person in results: add to list (skip DNC, skip already-member)
- Return count of added members
- Requires `require_role(current_user, ["admin", "standard_user", "rfp_team"])`

**Modify: `templates/distribution_lists/_tab_members.html`** (or member management section on detail page)
- Add "Add All Matching" button next to the search filters
- Button only appears when filters are active
- Confirmation dialog: "Add X people matching current filters to this list?"
- HTMX POST to the bulk endpoint, refresh member list on success

---

## Step 5.4: Follow-Up Task Assignment [Change 13]

Currently, when an activity has "Follow-Up Required" enabled, the auto-generated task is always assigned to the activity author. Allow the user to choose the assignee.

### Modify: `routers/activities.py`

- In `create_activity()` and `update_activity()`, when creating the follow-up task:
  - Check for `follow_up_assignee_id` in form data
  - If provided, use that user ID as the task assignee
  - If not provided, default to the activity author (current behavior)
- In the form context loading (new/edit), query coverage team members:
  - Get linked organizations from form data or existing activity
  - Get people with `coverage_owner` at those orgs
  - Get lead owners at those orgs
  - Deduplicate into a list of suggested assignees

### Modify: `templates/activities/form.html`

In the follow-up section (shown when Follow-Up Required is checked):
- Add "Assign To" dropdown below the follow-up notes
  - Default option: activity author (current user) — pre-selected
  - Options: all active users from the users table
  - Suggested assignees (coverage team) shown at top of dropdown with a visual separator
- The dropdown should be wrapped in the same `follow-up-fields` container that toggles visibility

---

## Step 5.5: Soft Delete Rename [Change 14]

Rename `is_archived` → `is_deleted` across all entity tables for clarity.

### Schema changes — add to `db/schema.sql`

Add ALTER TABLE statements (12 tables):
```sql
ALTER TABLE organizations RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE people RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE activities RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE leads RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE contracts RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE tasks RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE person_organization_links RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE activity_organization_links RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE activity_people_links RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE fee_arrangements RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE record_tags RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE documents RENAME COLUMN is_deleted TO is_deleted;  -- already named correctly
```

**Note:** `distribution_lists.is_active` stays as-is — it's a status field, not a soft-delete flag.

### Code changes — global replace

In **all routers** (`organizations.py`, `people.py`, `activities.py`, `leads.py`, `contracts.py`, `distribution_lists.py`, `tasks.py`, `dashboards.py`, `admin.py`, `documents.py`):
- Replace `.eq("is_archived", False)` → `.eq("is_deleted", False)`
- Replace `.update({"is_archived": True})` → `.update({"is_deleted": True})`
- Replace `.update({"is_archived": False})` → `.update({"is_deleted", False})`
- Replace any Python variable references to `is_archived`

In **`services/grid_service.py`**:
- Replace `is_archived` → `is_deleted` in `_execute_query()` filter

In **`services/form_service.py`**:
- Replace `is_archived` → `is_deleted` if referenced

In **`db/helpers.py`**:
- Replace any `is_archived` references

In **templates** — check for any template references to `is_archived` and replace.

### Add: Admin restore endpoint

**Modify: `routers/admin.py`**

Add endpoint: `POST /admin/{entity_type}/{record_id}/restore`
- Requires admin role
- Validates entity_type is one of the supported entities
- Sets `is_deleted = False` on the record
- Audit logs the restoration
- Returns redirect or HTMX response

This allows admins to un-delete records that were soft-deleted.

---

## Step 5.6: Duplicate Detection Enhancements [Change 15]

### Schema — add to `db/schema.sql`

```sql
CREATE TABLE duplicate_suppressions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type     TEXT NOT NULL,
    record_id_a     UUID NOT NULL,
    record_id_b     UUID NOT NULL,
    suppressed_by   UUID NOT NULL REFERENCES users(id),
    suppressed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(entity_type, record_id_a, record_id_b)
);
CREATE INDEX idx_dup_supp_entity ON duplicate_suppressions (entity_type);
```

### Modify: `routers/organizations.py` and `routers/people.py`

In the duplicate detection endpoints (`check-duplicates`):
1. After querying similar records, load suppressions for the current record
2. Filter out any matches where a suppression exists (in either direction: a→b or b→a)
3. Add a "Not a Duplicate" button next to each match in the duplicate warning partial

### Add: "Not a Duplicate" endpoints

**`POST /organizations/{org_id}/suppress-duplicate`**
**`POST /people/{person_id}/suppress-duplicate`**
- Accept `other_id` in form data
- Insert into `duplicate_suppressions` (normalize: always store smaller UUID as record_id_a)
- Audit log the suppression
- Return HTMX partial refreshing the duplicate list

### Modify: duplicate warning templates

Update `templates/organizations/_duplicate_warning.html` and `templates/people/_duplicate_warning.html`:
- Add "Not a Duplicate" button per match row
- Button uses `hx-post` to the suppress endpoint
- On success, the match row is removed from the list

### Add: Admin batch duplicate scan

**Modify: `routers/admin.py`**

Add endpoints:

**`GET /admin/duplicates/{entity_type}`** — Batch duplicate scan page
- Requires admin role
- Entity type must be `organization` or `person`
- Run the similarity function across all active records (paginated — top 50 pairs by similarity score)
- Exclude already-suppressed pairs
- Return page with duplicate pairs table

**`POST /admin/duplicates/{entity_type}/merge`** — Merge two records (stretch goal)
- Requires admin role
- Accept `keep_id` and `merge_id`
- For organizations: update all `organization_id` FKs on people, activities, leads, contracts, distribution_list_members to point to `keep_id`; soft-delete `merge_id`
- For people: update all person FKs on activity_people_links, distribution_list_members to point to `keep_id`; soft-delete `merge_id`
- Audit log every change
- **This is complex — implement as a stretch goal if time permits. The scan + suppress is the MVP.**

### Create: `templates/admin/duplicates.html`

Admin duplicate scan page:
- Entity type selector (Organizations / People tabs)
- Table of duplicate pairs: Record A name, Record B name, Similarity Score, Actions (View A, View B, Not a Duplicate, Merge)
- Pagination
- "Not a Duplicate" uses HTMX to suppress and remove the row
- "Merge" opens a confirmation modal showing which record to keep (stretch goal)

---

## Important Rules

1. **Read `Echo2/CLAUDE.md`** for coding standards — all rules apply (soft deletes, audit logging, reference_data for dropdowns, HTMX partials for `HX-Request`, no hardcoded dropdown values, etc.).
2. **All existing functionality must continue working unchanged.** Every current page, form, filter, and HTMX interaction must be preserved.
3. **HTMX partials**: When the request has `HX-Request` header, return only the relevant partial (not the full page).
4. **Audit log all changes** to reference_data, duplicate suppressions, contract creation, task assignment, and record restoration.
5. **Step 5.5 (soft delete rename) must be done as a single atomic change** — update schema, all routers, all services, all templates in one pass to avoid inconsistency. Use `replace_all` for bulk text replacement.
6. **After completing all steps, STOP and present results for manual review.** Do not proceed without approval.

---

## Execution Order

Execute in this order to minimize conflicts:

1. **Step 5.0** — Reference Data Admin CRUD (self-contained, no dependencies)
2. **Step 5.1** — Lead Finder Saved View (depends on grid_service virtual columns)
3. **Step 5.2** — Lead→Contract Manual Creation (modifies leads + contracts routers)
4. **Step 5.3** — Distribution List Improvements (modifies people + dist lists)
5. **Step 5.4** — Follow-Up Task Assignment (modifies activities router)
6. **Step 5.5** — Soft Delete Rename (global rename — do last to avoid merge conflicts with other steps)
7. **Step 5.6** — Duplicate Detection Enhancements (modifies orgs, people, admin)

---

## Verification Checklist

After completion, verify:

- [ ] Reference Data: can browse categories, create/edit/toggle/reorder values, hierarchical categories work
- [ ] Lead Finder: org grid shows "Active Leads" count column, clicking expands leads panel
- [ ] Contract creation: manual create from Won lead works, auto-create removed
- [ ] Person detail: Distribution Lists tab shows memberships
- [ ] Bulk add: "Add All Matching" adds filtered people to distribution list
- [ ] Follow-up assignment: activity form shows assignee dropdown, task uses selected assignee
- [ ] Soft delete: all `is_archived` references replaced with `is_deleted`, no regressions
- [ ] Admin restore: can restore soft-deleted records
- [ ] Duplicate suppression: "Not a Duplicate" works on org/person forms
- [ ] Admin duplicate scan: batch scan page shows pairs, can suppress
- [ ] All existing pages still load and function correctly

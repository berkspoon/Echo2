# Phase 4: Reusable Grid Component

Execute **Phase 4** from `Echo2/echo2/Patrick Implementation Plan.md` — **"Reusable Grid Component"** (Change 8). Read `Echo2/CLAUDE.md` for coding standards and project context.

**Depends on:** Phase 3 Step 3.2 (field_definitions consumed by forms — already complete).

---

## Step 4.1: Grid Component Templates

### Create: `templates/components/_grid.html`

A single, reusable Jinja2 macro that renders any entity's list view. Accepts:

- `columns` — list of field definition dicts (from `field_defs`) describing which columns to show
- `rows` — list of record dicts (already enriched with display values)
- `entity_type` — string (e.g. `"organization"`, `"lead"`)
- `pagination` — dict with `page`, `page_size`, `total`, `total_pages`
- `sort_by` — current sort column name
- `sort_dir` — `"asc"` or `"desc"`
- `filters` — dict of currently active filters `{field_name: value}`
- `base_url` — the list endpoint URL (e.g. `/organizations`, `/leads/my-leads`)
- `saved_views` — list of saved view dicts for the view selector
- `current_view_id` — UUID of the currently active saved view (or `None`)
- `extra_columns` — optional list of extra non-field-def columns (e.g. computed columns like "Active Leads" count) with `{name, label, sortable, render_html}`

**Features to implement:**

1. **Sortable column headers** — clicking a header toggles sort. Use HTMX `hx-get` with `sort_by` and `sort_dir` query params. Show up/down indicator on active sort column. Target `#grid-container` for partial swap.

2. **Per-column filters** — type-aware filter inputs rendered in a filter row below headers:
   - `text`, `textarea`, `email`, `url`, `phone` → text search input (debounced 300ms via `hx-trigger="keyup changed delay:300ms"`)
   - `dropdown`, `multi_select` → select dropdown populated from `fd.options`
   - `lookup` (user fields) → select dropdown populated from users list
   - `date` → two date inputs (from / to) for date range
   - `number`, `currency` → two number inputs (min / max) for range
   - `boolean` → select with "All" / "Yes" / "No"
   - All filters use HTMX to reload the grid with the filter applied as query params

3. **Column show/hide** — include the `_column_selector.html` component (see below). Toggling columns reloads the grid via HTMX.

4. **Saved View selector** — dropdown at top of grid showing available views. Selecting a view navigates to `?view_id=<uuid>`. Include "Save Current View" and "Reset to Default" actions.

5. **HTMX-driven pagination** — page navigation at bottom, swaps `#grid-container`. Show "Showing X-Y of Z" text and page size selector (25 / 50 / 100).

6. **Row click navigation** — each row links to the entity detail page (`/<entity_type>/<id>`). Preserve the existing behavior where rows are clickable.

7. **Batch actions toolbar** (optional, admin only) — checkbox column, select all, bulk archive button. Only show if user has archive permission.

8. **Empty state** — "No records found" message with link to create new if user has permission.

9. **Cell rendering** — use field_type metadata to format cell values:
   - `currency` → `$X,XXX.XX`
   - `date` → formatted date string
   - `boolean` → green check / red X icon
   - `dropdown` → display the option label, not raw value
   - `lookup` (user) → display name
   - `url` → clickable link (truncated)
   - `multi_select` → comma-separated labels or badge pills
   - Truncate long text fields to ~80 chars with ellipsis

10. **Preserve entity-specific badges/styling** — the grid should support an optional `row_class` callback or template block for entity-specific row styling (e.g., overdue task highlighting, stage color badges on leads). Implement via a `render_cell` block or by allowing `extra_columns` with pre-rendered HTML.

### Create: `templates/components/_column_selector.html`

A dropdown panel macro listing all available fields for the entity (from `field_defs`). Each field has a checkbox to toggle visibility. Changes trigger HTMX reload with `visible_columns` param (comma-separated field names).

- Group fields by section (matching field_definitions sections)
- Show field display_name with field_type icon/badge
- "Select All" / "Deselect All" buttons
- Current visible columns are pre-checked

---

## Step 4.2: Saved Views

### Schema — Add `saved_views` table to `db/schema.sql`:

```sql
CREATE TABLE saved_views (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id),
    entity_type     TEXT NOT NULL,
    view_name       TEXT NOT NULL,
    columns         JSONB NOT NULL DEFAULT '[]',
    filters         JSONB NOT NULL DEFAULT '{}',
    sort_by         TEXT,
    sort_dir        TEXT NOT NULL DEFAULT 'asc',
    is_default      BOOLEAN NOT NULL DEFAULT FALSE,
    is_shared       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_sv_user_entity ON saved_views (user_id, entity_type);
CREATE TRIGGER trg_saved_views_updated BEFORE UPDATE ON saved_views FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

### Create: `services/grid_service.py`

Central service that replaces per-router list logic. Functions:

#### `build_grid_context(entity_type, request, user, saved_view_id=None) -> dict`

This is the main function that every list route will call. It:

1. **Loads field definitions** for the entity type (via `get_field_definitions` + `enrich_field_definitions`)
2. **Loads saved view** if `saved_view_id` is provided (or the user's default view for the entity, or falls back to showing all core columns)
3. **Determines visible columns** — from saved view, or `visible_columns` query param, or default (all fields where `show_in_list` or first ~8 fields)
4. **Extracts filters** from query params (each field_name can be a query param, date ranges use `field__from` / `field__to`, number ranges use `field__min` / `field__max`)
5. **Extracts sort** from `sort_by` and `sort_dir` query params (with defaults)
6. **Extracts pagination** from `page` and `page_size` query params (defaults: page=1, page_size=25)
7. **Builds the Supabase query** — applies filters, sort, pagination, soft-delete filter (`is_archived=False`), and any entity-specific base filters (e.g., `lead_type` for advisory vs fundraise views, `assigned_to` for "My Tasks")
8. **Enriches rows** — resolves lookup fields (user names, org names), loads EAV values for custom fields, formats display values
9. **Loads saved views** for the view selector dropdown (user's own views + shared views for this entity)
10. **Returns** context dict: `{ columns, rows, pagination, sort_by, sort_dir, filters, saved_views, current_view_id, entity_type, base_url, users }`

#### `save_view(user_id, entity_type, view_name, columns, filters, sort_by, sort_dir, is_shared=False) -> dict`

Creates or updates a saved view. If `is_default=True`, unset any other default view for this user+entity.

#### `delete_view(view_id, user_id) -> bool`

Deletes a saved view. Only the owner can delete (or admin).

#### `get_default_columns(entity_type, field_defs) -> list[str]`

Returns the default visible column names for an entity when no saved view is active. Use the existing list page columns as the defaults (i.e., whatever each entity's `_list_table.html` currently shows).

### Saved View Endpoints — Add to `routers/admin.py` or create `routers/views.py`:

- `POST /views/save` — save current grid state as a view
- `POST /views/{view_id}/delete` — delete a saved view
- `POST /views/{view_id}/set-default` — mark view as default

---

## Step 4.3: Deploy Grid on All Entities

**Modify** every entity's list route to use `grid_service.build_grid_context()`. Each list handler should shrink from ~60-80 lines to ~15 lines. The pattern:

```python
@router.get("")
async def list_items(request: Request, current_user = Depends(get_current_user)):
    require_role(current_user, [...])
    ctx = build_grid_context("entity_type", request, current_user)
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("components/_grid.html", {"request": request, **ctx})
    return templates.TemplateResponse("entity/list.html", {"request": request, "user": current_user, **ctx})
```

### Entity-specific considerations:

| Entity | Default Columns | Special Behavior |
|--------|----------------|------------------|
| **Organizations** | company_name, organization_type, hq_location, employee_count, aum | "My Organizations" filters by coverage |
| **People** | first_name, last_name, primary org, title, email, phone | "My People" filters by coverage_owner |
| **Leads (Advisory)** | org name, summary, rating/stage, service_type, aksia_owner, expected_revenue | Filter `lead_type='advisory'`. "My Leads" filters by aksia_owner_id |
| **Leads (Fundraise)** | org name, fund ticker, share_class, stage, target_allocation, soft_circle, aksia_owner | Filter `lead_type IN ('fundraise','product')`. Reuse Capital Raise sidebar link |
| **Activities** | title, type, date, author, linked orgs | "My Activities" filters by author + coverage |
| **Contracts** | org name, service_type, status, start_date, actual_revenue | No "My" view |
| **Tasks** | title, status, due_date, assigned_to, source, linked record | "My Tasks" filters by assigned_to. Preserve overdue row highlighting (`bg-red-50`) |
| **Distribution Lists** | name, type, brand, member count, is_official | No "My" view |

### Modify all `list.html` templates:

Replace the entity-specific table include with:
```jinja2
{% include "components/_grid.html" %}
```

Keep entity-specific content above the grid (e.g., filter tabs like "My X / All X", "Advisory / Fundraise" toggle, "New" button).

### Delete old partials:

After confirming the grid works for each entity, delete these 8 `_list_table.html` partial files:
- `templates/organizations/_list_table.html`
- `templates/people/_list_table.html`
- `templates/leads/_list_table.html`
- `templates/activities/_list_table.html`
- `templates/contracts/_list_table.html`
- `templates/tasks/_list_table.html`
- `templates/distribution_lists/_list_table.html`

**Do NOT delete** any dashboard widget partials — dashboards have their own widget templates that are independent of the grid.

---

## Important Rules

1. **Read `Echo2/CLAUDE.md`** for coding standards — all rules apply (soft deletes, audit logging, reference_data for dropdowns, HTMX partials for `HX-Request`, no hardcoded dropdown values, etc.).
2. **All existing functionality must continue working unchanged.** The grid is a drop-in replacement — every filter, sort, pagination, "My X" view, and entity-specific behavior that exists today must be preserved.
3. **HTMX partials**: When the request has `HX-Request` header, return only the `_grid.html` partial (not the full page). This enables HTMX-driven sort, filter, and pagination without full page reloads.
4. **Entity-specific enrichment**: Some entities need special enrichment (e.g., resolving org names on leads, fund tickers on fundraise leads, primary org on people, linked record names on tasks). The grid service must support entity-specific enrichment hooks or handle these in the query.
5. **Batch resolution**: Use batch queries (not N+1) for resolving lookup values. The existing `batch_resolve_users`, `batch_resolve_orgs` helpers in `db/helpers.py` should be leveraged.
6. **EAV values**: Custom (EAV) fields must be loadable in grid context. Use `load_custom_values_batch` from `db/field_service.py` for efficient batch loading.
7. **Backward compatibility**: If a saved view references a field that has since been deactivated, skip it gracefully (don't error).
8. **After completing all steps, STOP and present results for manual review.** Do not proceed to Phase 5 without approval.

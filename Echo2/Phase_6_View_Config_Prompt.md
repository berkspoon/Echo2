# Phase 6: Admin-Configurable View Settings

Read `Echo2/CLAUDE.md` and `Echo2/feedback.md` for full project context. This prompt implements admin-configurable view settings so admins can customize filters, table columns, and dropdown options without code changes.

## Why This Is Needed
Currently ~20 view elements (filter fields, table columns, dropdown options) are hardcoded in Python and templates. After deployment, admins need to add/remove filter fields in the distribution list builder, toggle table columns on dashboards (e.g., show "Fund(s)" on hot prospects only for the All Funds view), and change grid default columns — all without developer involvement.

## What Was Already Built
- `field_definitions` table — admin-managed fields per entity (Admin > Fields)
- `page_layouts` table — admin-managed form section layouts (Admin > Layouts)
- `saved_views` table — user-managed screeners (grid column/filter/sort configs)
- `reference_data` table — admin-managed dropdown values
- Admin panel at `/admin/` with Fields, Layouts, Roles, Users, Duplicates sections
- Distribution list filter builder (Phase 5) — `_build_filter_fields()` in `routers/distribution_lists.py` reads person `field_definitions` + hardcoded `_ORG_FILTER_FIELDS` list
- Dashboard tables (hot prospects, investor breakdown, declined) with hardcoded columns in templates
- Grid default columns hardcoded in `_DEFAULT_COLUMNS` dict in `services/grid_service.py`

## What to Build

### Step 1: Schema + Service

**Table DDL** (add to `db/migrate_schema.sql` AND `db/schema.sql`):
```sql
CREATE TABLE IF NOT EXISTS view_configurations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    view_key        TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    description     TEXT,
    category        TEXT NOT NULL DEFAULT 'general',
    config          JSONB NOT NULL DEFAULT '{}',
    updated_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_vc_key ON view_configurations (view_key);
```

**New file `db/view_config_service.py`** — follow the pattern of `db/field_service.py`:
- `get_view_config(view_key, default=None)` — returns config JSONB, falls back to `default` if no row exists
- `get_all_view_configs()` — returns all rows for admin listing
- `save_view_config(view_key, config, updated_by)` — updates config JSONB
- Simple in-process dict cache, busted on save

### Step 2: Seed Defaults

**New file `scripts/seed_view_configurations.py`** — seeds ~15 rows with current hardcoded values. Upsert with `ON CONFLICT DO NOTHING`. `--force` to overwrite.

View keys:

| view_key | category | description |
|----------|----------|-------------|
| `dl_filter_fields` | distribution_lists | Which person + org fields appear in DL filter builder |
| `cr_hot_prospects_columns` | dashboards | Hot prospects table columns with conditional visibility |
| `cr_investor_breakdown_columns` | dashboards | Investor breakdown table columns |
| `cr_declined_columns` | dashboards | Declined prospects table columns |
| `cr_group_by_options` | dashboards | Capital raise group-by dropdown options |
| `advisory_metric_options` | dashboards | Advisory pipeline metric selector options |
| `grid_defaults.organization` | grids | Default visible columns for org grid |
| `grid_defaults.person` | grids | Default visible columns for person grid |
| `grid_defaults.lead` | grids | Default visible columns for lead grid |
| `grid_defaults.activity` | grids | Default visible columns for activity grid |
| `grid_defaults.contract` | grids | Default visible columns for contract grid |
| `grid_defaults.task` | grids | Default visible columns for task grid |
| `grid_defaults.distribution_list` | grids | Default visible columns for DL grid |

**Config shapes:**

DL filter fields:
```json
{
  "person_fields": [],
  "org_fields": [
    {"field_name": "org_city", "display_name": "Org City", "field_type": "text", "dropdown_category": null},
    {"field_name": "org_country", "display_name": "Org Country", "field_type": "dropdown", "dropdown_category": "country"},
    {"field_name": "org_type", "display_name": "Org Type", "field_type": "dropdown", "dropdown_category": "organization_type"},
    {"field_name": "org_aum_mn", "display_name": "Org AUM ($M)", "field_type": "number", "dropdown_category": null}
  ],
  "include_field_types": ["text", "email", "phone", "url", "textarea", "dropdown", "multi_select", "number", "currency", "date", "boolean", "text_list"]
}
```
- `person_fields`: empty = all active person fields shown (current default). Non-empty = whitelist.
- `org_fields`: replaces hardcoded `_ORG_FILTER_FIELDS`.
- `include_field_types`: which field types are filterable. Admin adds `"lookup"` here to enable coverage_owner filtering.

Dashboard table columns (e.g., `cr_hot_prospects_columns`):
```json
{
  "columns": [
    {"key": "org_name", "label": "Organization", "render_type": "link"},
    {"key": "stage_label", "label": "Stage", "render_type": "badge"},
    {"key": "owner_name", "label": "Lead Owner", "render_type": "text"},
    {"key": "allocation_fmt", "label": "Allocation ($M)", "render_type": "currency_right"},
    {"key": "tickers_str", "label": "Fund(s)", "render_type": "mono", "visible_when": {"current_fund_ticker": ""}}
  ]
}
```
- `render_type`: `text`, `link`, `badge`, `currency_right`, `mono` — controls template rendering
- `visible_when`: optional condition dict. `{"current_fund_ticker": ""}` = show only when no specific fund selected (All Funds)

Option lists (e.g., `cr_group_by_options`):
```json
{
  "options": [
    {"value": "stage", "label": "Stage"},
    {"value": "lp_type", "label": "LP Type"},
    {"value": "country", "label": "Country"},
    {"value": "fund", "label": "Fund"}
  ]
}
```

Grid defaults (e.g., `grid_defaults.organization`):
```json
{"columns": ["company_name", "relationship_type", "organization_type", "country", "aum_mn"]}
```

### Step 3: Admin UI

**3 routes in `routers/admin.py`:**
- `GET /admin/views` — list all configs grouped by category
- `GET /admin/views/{view_key}/edit` — edit form
- `POST /admin/views/{view_key}` — save config

**Sidebar link in `templates/base.html`:** Add "Views" between "Layouts" and "Duplicates" in the admin section.

**Template `templates/admin/views.html`:** List page grouped by category. Each row: display_name, description, category badge, last updated. Edit link per row.

**Template `templates/admin/view_config_form.html`:** Edit page with editors based on config category:
- **Column list** (dashboard tables): table rows with checkbox, label input, render_type dropdown, optional visible_when. Add/remove/reorder.
- **Option list** (group-by, metrics): value/label pairs. Add/remove/reorder.
- **Field list** (DL filters): person field checkboxes, org virtual fields table, field type checkboxes.
- **Entity column list** (grid defaults): field checkboxes with reorder arrows (like existing `_column_selector.html`).

### Step 4: Wire Consumers

Every consumer calls `get_view_config(key, default=HARDCODED_FALLBACK)`. Zero-downtime: if no DB row exists, hardcoded default is used.

**4a. DL Filter Builder** (`routers/distribution_lists.py`):
- `_build_filter_fields()` reads `dl_filter_fields` config
- Add `"lookup"` to `_OPERATORS_BY_TYPE`: `[("eq", "Equals"), ("neq", "Not equals"), ("is_empty", "Is empty"), ("is_not_empty", "Is not empty")]`
- For lookup fields, load active users as dropdown options
- Filter builder template: lookup fields render user-select dropdown

**4b. Dashboard Tables** (`routers/dashboards.py` + `capital_raise.html`):
- `_render_capital_raise()` loads column configs, filters by `visible_when` conditions against context
- Python prepares ALL possible data keys in each dict (including `tickers_str` for Fund column)
- Template iterates config columns with render_type conditional:
```html
{% for col in hot_prospect_columns %}
{% if col.render_type == 'link' %}<td><a href="...">{{ hp[col.key] }}</a></td>
{% elif col.render_type == 'badge' %}<td><span class="badge...">{{ hp[col.key] }}</span></td>
{% elif col.render_type == 'currency_right' %}<td class="text-right">${{ hp[col.key] }}</td>
{% elif col.render_type == 'mono' %}<td><span class="font-mono...">{{ hp[col.key] }}</span></td>
{% else %}<td>{{ hp[col.key] }}</td>{% endif %}
{% endfor %}
```

**4c. Capital Raise Group-By** (`capital_raise.html`): Replace hardcoded `<option>` tags with `{% for opt in cr_group_by_options %}`.

**4d. Advisory Metrics** (`_advisory_content.html`): Replace hardcoded metric `<option>` tags with loop.

**4e. Grid Defaults** (`services/grid_service.py`): In `_resolve_visible_columns()`, call `get_view_config(f"grid_defaults.{entity_type}", default={"columns": _DEFAULT_COLUMNS[entity_type]})`.

## Implementation Order
1. Schema + service + seed script (no functional change)
2. Admin UI (routes + templates + sidebar)
3. Wire DL filter builder + lookup support
4. Wire dashboard tables (hot prospects, investor, declined)
5. Wire CR group-by + advisory metrics
6. Wire grid default columns

## Key Files
- `db/migrate_schema.sql` + `db/schema.sql` — table DDL
- `db/view_config_service.py` — new service
- `scripts/seed_view_configurations.py` — new seed script
- `routers/admin.py` — 3 new routes
- `templates/admin/views.html` + `view_config_form.html` — new templates
- `templates/base.html` — sidebar link
- `routers/distribution_lists.py` — wire filter builder + lookup operators
- `routers/dashboards.py` — wire tables + options
- `templates/dashboards/capital_raise.html` — config-driven columns + options
- `templates/dashboards/_advisory_content.html` — config-driven metrics
- `services/grid_service.py` — wire `_DEFAULT_COLUMNS`

## After Completing
1. Update `Echo2/CLAUDE.md` — add session notes
2. Update `Echo2/feedback.md` — if applicable
3. Pause for context clear

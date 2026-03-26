# Phase 2: Dashboard Configurability — Josh Feedback

Read `Echo2/CLAUDE.md` and `Echo2/feedback.md` for full project context. This prompt implements Phase 2 of Josh's feedback: dashboard configurability enhancements.

## What Was Done in Phase 1
- **Bug fix: Drill-down column change** — Both advisory and capital raise drilldown endpoints in `routers/dashboards.py` now detect grid-internal reloads (requests with `visible_columns`, `sort_by`, or `page_size` params) and return just `components/_grid.html` instead of the full drilldown wrapper template.
- **Bug fix: DL filter auto-adds everyone** — `save_list_filters` in `routers/distribution_lists.py` now validates that at least one `cf_*` column filter or `q` search text exists before saving. UI in `_filter_editor.html` shows warning when no filters applied.

## Phase 2 Tasks (5 items)

### 2A. Metric Selector on Advisory Pipeline

**Goal:** Let users choose what the pipeline bars represent: lead count, expected revenue, or Yr1 FLAR.

**Current code:** `_group_advisory_leads(all_leads, group_by)` at ~line 640 of `routers/dashboards.py` hardcodes `total_revenue` as the bar sizing metric. Line 726: `max_revenue`, line 739: `bar_pct = _pct(g["total_revenue"], max_revenue)`. Bar labels show `{{ item.count }} leads · ${{ item.revenue_fmt }}` in `_advisory_chart.html` line 14.

**Changes needed:**
1. `routers/dashboards.py`:
   - Add `metric="revenue"` param to `_group_advisory_leads(all_leads, group_by, metric="revenue")`.
   - Track `total_flar` alongside `total_revenue` in the grouping loop (sum `expected_yr1_flar`).
   - Compute `bar_pct` based on selected metric: if `metric=="count"`, use `g["count"]/max_count*100`; if `metric=="flar"`, use `g["total_flar"]/max_flar*100`; else use revenue.
   - Add `metric_value` and `metric_fmt` to each bar dict for the template label.
   - `advisory_pipeline_chart()` endpoint (~line 923): accept `metric: str = Query("revenue")` param, pass to `_group_advisory_leads()`.
   - `advisory_pipeline_drilldown()` endpoint (~line 958): accept `metric` param, include in `drilldown_base_url`, pass through.
   - `advisory_pipeline()` main endpoint (~line 749): accept and pass `metric` param.

2. `templates/dashboards/_advisory_content.html`:
   - Add a metric `<select>` next to the group-by selector (lines 28-39). Options: `<option value="count">Lead Count</option>`, `<option value="revenue">Expected Revenue ($)</option>`, `<option value="flar">Yr1 FLAR ($)</option>`. Include it in the `hx-include` directive.

3. `templates/dashboards/_advisory_chart.html`:
   - Line 14: make bar label conditional on `metric` context var. When metric=count, show "X leads" as primary. When metric=revenue, show "$revenue" as primary with count in parentheses. When metric=flar, show "$FLAR" as primary.
   - Include `metric` in the drilldown `hx-get` URL.

### 2B. Dashboard Presets (Saved Dashboard Views)

**Goal:** Let users save the current dashboard filter state as a named preset. "Focus Pipeline" is just a preset with `stage=focus`. Reuse the existing `saved_views` table with pseudo-entity-types `dashboard_advisory` and `dashboard_capital_raise`.

**Current code:** `saved_views` table has `user_id`, `entity_type`, `view_name`, `columns` (JSONB), `filters` (JSONB), `sort_by`, `sort_dir`, `is_default`, `is_shared`. The `url_map` in `routers/views.py` line 69-78 maps entity_type to redirect URL.

**Changes needed:**
1. `routers/views.py`:
   - Add to `url_map`: `"dashboard_advisory": "/dashboards/advisory-pipeline"`, `"dashboard_capital_raise": "/dashboards/capital-raise"`.

2. `routers/dashboards.py`:
   - Add `GET /dashboards/advisory-pipeline/presets` — loads `saved_views` where `entity_type='dashboard_advisory'` for current user (own + shared). Returns HTMX partial.
   - The save uses the existing `POST /views/save` endpoint (already handles any entity_type). Store dashboard filters in the `filters` JSONB and display settings (group_by, metric) in `columns` JSONB.

3. `templates/dashboards/advisory_pipeline.html`:
   - Add a preset selector dropdown above the filter bar. Load via HTMX from `/dashboards/advisory-pipeline/presets`.
   - Each preset is a link that loads the dashboard with saved filter params appended to the URL.
   - Add "Save Preset" button that opens a modal (name input, share checkbox). The form POSTs to `/views/save` with `entity_type=dashboard_advisory`.

4. Apply same pattern to capital raise dashboard if time permits.

### 2C. Capital Raise — Country Group-By

**Goal:** Add "Country" as a group-by dimension on the capital raise pipeline chart.

**Current code:** `_group_capital_raise_prospects(prospects, group_by)` at ~line 1098 supports `stage`, `lp_type`, `fund`. Org data is already batch-resolved via `batch_resolve_orgs()` for `lp_type` case (line 1113-1115).

**Changes needed:**
1. `routers/dashboards.py`:
   - `_group_capital_raise_prospects()`: add `elif group_by == "country":` case. Resolve org data (reuse same `batch_resolve_orgs()` pattern as `lp_type`). Group by `org_data.get("country", "Unknown")`.
   - Load country labels from `get_reference_data("country")` for label resolution.
   - `capital_raise_drilldown()` (~line 1210): add `"country"` to filtering logic. When `dimension == "country"`, resolve orgs, filter prospects whose org country matches `value`. Add to `dim_labels`: `"country": "Country"`.

2. `templates/dashboards/capital_raise.html`:
   - Add `<option value="country">Country</option>` to the group-by selector (line 97-100).

### 2D. Capital Raise — Owner Filter

**Goal:** Add an owner dropdown to the capital raise dashboard so users can see their personal pipeline.

**Current code:** Advisory pipeline has an owner filter (`owner: str = Query("")` at line 755) and a users dropdown in the template. Capital raise has no owner filter — `_load_capital_raise_prospects()` only filters by `fund_ticker`.

**Changes needed:**
1. `routers/dashboards.py`:
   - `_load_capital_raise_prospects(fund_ticker, owner=None)`: add optional `owner` param. If set, add `.eq("aksia_owner_id", owner)` to the query.
   - `_render_capital_raise(request, current_user, fund_ticker, owner=None)`: accept and pass `owner`.
   - `capital_raise_all()` and `capital_raise_fund()`: accept `owner: str = Query("")` param.
   - `capital_raise_chart()`: accept `owner` param, pass to `_load_capital_raise_prospects()`.
   - `capital_raise_drilldown()`: accept `owner` param, pass through.
   - Load users list in `_render_capital_raise()` (same as advisory pipeline line 862).

2. `templates/dashboards/capital_raise.html`:
   - Add a filter bar below the fund tabs with owner dropdown. The dropdown should include a "My Pipeline" option that pre-selects the current user.
   - Dropdown fires HTMX full page reload with `owner` param.
   - Include `owner` in chart and drilldown `hx-vals`.

### 2E. Capital Raise — Traction Highlighting ("Hot Prospects")

**Goal:** Surface organizations with the most pipeline traction — those in advanced fundraise stages.

**Traction scoring:**
- `target_identified` / `intro_scheduled` = 0
- `initial_meeting_complete` = 1
- `ddq_materials_sent` = 2
- `due_diligence` = 3
- `ic_review` = 4
- `soft_circle` / `legal_docs` / `closed` = 5
- `declined` = 0

**Changes needed:**
1. `routers/dashboards.py`:
   - Add `_TRACTION_SCORES` dict mapping stages to scores.
   - Add `_compute_traction_score(stage)` helper.
   - In `_render_capital_raise()`: compute traction per prospect, build `hot_prospects` list (traction >= 3, sorted desc). Group by org — show org name, highest stage, fund ticker(s), allocation total.
   - Optionally add `"traction"` as a group-by dimension in `_group_capital_raise_prospects()`.

2. `templates/dashboards/capital_raise.html`:
   - Add "Hot Prospects" card section between the pipeline chart and investor breakdown.
   - Show traction badges: green bg for score 5, amber for 3-4.
   - Show org name, current stage, fund, allocation.
   - Only render section if `hot_prospects` is non-empty.

## Key Files
- `echo2/routers/dashboards.py` — all dashboard logic (1400+ lines)
- `echo2/routers/views.py` — screener/saved views CRUD
- `echo2/services/grid_service.py` — grid service (for `build_grid_context` used by drilldowns)
- `echo2/templates/dashboards/advisory_pipeline.html` — full advisory page
- `echo2/templates/dashboards/_advisory_content.html` — advisory content partial
- `echo2/templates/dashboards/_advisory_chart.html` — advisory chart bars
- `echo2/templates/dashboards/capital_raise.html` — full capital raise page
- `echo2/templates/dashboards/_capital_raise_chart.html` — capital raise chart bars
- `echo2/db/helpers.py` — `batch_resolve_orgs()`, `batch_resolve_users()`, `get_reference_data()`

## After Completing Phase 2
1. Update `Echo2/CLAUDE.md` — add session notes
2. Update `Echo2/feedback.md` — mark items `[x]`
3. Write `Echo2/Phase_3_Josh_Prompt.md` for Grid Bulk Operations
4. Pause for context clear

# Phase 5: Outstanding Fixes — Josh Feedback

Read `Echo2/CLAUDE.md` and `Echo2/feedback.md` for full project context. This prompt addresses remaining items from Josh's feedback testing.

## What Was Done Previously
- **Phases 1-4:** Bug fixes, dashboard configurability, grid bulk operations, Excel export
- **Bug fix round:** Drilldown URL corruption, presets 500, bulk edit lookup/dropdown, metric defaults, group-by persistence, preset delete

## Outstanding Items

### 5A. Distribution List Filter Editor Redesign

**Problem:** The current filter editor embeds a full people grid inside the DL detail page. When the user clicks "Apply" on the column selector, the page navigates away from the filter editor (back to the DL detail page without the filter section). The filter approach requires users to DISTILL with column filters, which is confusing.

**Goal:** Redesign toward a filter-BUILDER UX (similar to HubSpot segments). Users select field + operator + value(s) to define who should be on the list. No need for the full grid approach.

**Changes needed:**
1. Replace `templates/distribution_lists/_filter_editor.html` with a filter-builder form:
   - Each filter row: Field dropdown (from person field_definitions + org virtual fields) + Operator dropdown (contains, equals, not equals, in, not in — varies by field type) + Value input (text, dropdown, multi-select depending on field type)
   - "Add filter" button to add more rows (AND logic between rows)
   - "Remove" button per row
   - Live preview count: after each filter change, HTMX request to a preview endpoint showing "X people match"
   - "Save Filters" button saves the filter criteria

2. `routers/distribution_lists.py`:
   - Update `filter_editor` endpoint to return the new builder template with current filter criteria pre-populated
   - Add `POST /{list_id}/preview-filter-count` endpoint that receives filter criteria JSON and returns the count of matching people (reuse `_resolve_dynamic_members`)
   - Update `save_list_filters` to accept the new filter format (array of {field, operator, value} objects stored as `filter_criteria` JSONB)
   - Update `_resolve_dynamic_members` to handle the new filter format

3. Filter criteria format (stored in `filter_criteria` JSONB):
   ```json
   {
     "filters": [
       {"field": "country", "operator": "in", "value": ["US", "GB"]},
       {"field": "job_title", "operator": "contains", "value": "Director"},
       {"field": "org_type", "operator": "eq", "value": "pension_fund"}
     ]
   }
   ```

### 5B. Capital Raise Dashboard Improvements

**Changes needed:**
1. **Default to active leads** — Exclude "closed" and "declined" stages from the default capital raise view. Add a toggle/filter (like advisory pipeline's "Active Only" / "All" / "Inactive") so users can optionally see closed/declined.
   - In `_render_capital_raise()` and `_load_capital_raise_prospects()`, add `active_filter` param
   - Default: exclude closed + declined
   - Add Status dropdown to capital raise template (Active / All / Closed+Declined)

2. **Sort capital raise chart by allocation amount** — Default sort for capital raise bars should be by `total_allocation` descending (not stage order). When grouped by stage, keep stage order; for other group-bys, sort by allocation.

3. **Hot Prospects tweaks:**
   - Remove "Fund(s)" column from hot prospects table
   - Add "Lead Owner" column (resolve `aksia_owner_id` via `batch_resolve_users`)
   - Add filter dropdowns above hot prospects table: Lead Owner dropdown + Stage dropdown
   - These filters are client-side JS (filter the table rows without server round-trip)

### 5C. Advisory Pipeline — Group-By in Drilldown Header

**Current issue:** When grouped by "Relationship" and user clicks a bar, the drilldown header says "Stage: New" instead of "Relationship: New". The `drilldown_dimension` label needs to match the current group_by, and the `drilldown_value` should use the resolved label (not the raw key).

**Fix:** The drilldown endpoint already resolves `dim_labels` from groupable fields. Verify the dimension param flows correctly from the chart link through to the drilldown template.

## Key Files
- `echo2/templates/distribution_lists/_filter_editor.html` — replace with filter builder
- `echo2/routers/distribution_lists.py` — filter builder endpoints, updated `_resolve_dynamic_members`
- `echo2/templates/dashboards/capital_raise.html` — active filter, hot prospects tweaks
- `echo2/routers/dashboards.py` — `_load_capital_raise_prospects` active filter, chart sort
- `echo2/templates/dashboards/_advisory_chart.html` — verify drilldown dimension param

## After Completing Phase 5
1. Update `Echo2/CLAUDE.md` — add session notes
2. Update `Echo2/feedback.md` — mark items `[x]`
3. Pause for context clear

# Phase 4: Data Export to Excel — Josh Feedback

Read `Echo2/CLAUDE.md` and `Echo2/feedback.md` for full project context. This prompt implements Phase 4 of Josh's feedback: data export to Excel.

## What Was Done in Phases 1-3
- **Phase 1:** Bug fixes (drill-down column change, DL filter auto-adds everyone)
- **Phase 2:** Dashboard configurability (metric selector, dashboard presets, country group-by, owner filter, hot prospects traction highlighting)
- **Phase 3:** Grid bulk operations (row checkboxes, select all, floating bulk action bar, bulk edit, bulk delete)

## Phase 4 Task

### 4A. Export to Excel Button

**Goal:** Add an "Export" button to the grid toolbar that downloads the current grid data (respecting active filters, column selection, and sort order) as an `.xlsx` file.

**Current code:** `components/_grid.html` has a toolbar row with screener selector, column selector, and page size selector. No export functionality exists.

**Changes needed:**
1. Add `openpyxl` to `requirements.txt` (pure Python Excel writer, no C dependencies).

2. `routers/views.py`:
   - Add `GET /views/export/{entity_type}` endpoint. Accepts same query params as grid (visible_columns, sort_by, sort_dir, cf_* filters, search q, view_id).
   - Reuse `build_grid_context()` from `grid_service.py` but with `page_size=99999` (export all matching rows, not just current page).
   - Build an openpyxl Workbook: header row from column display_names, data rows with plain values (no HTML badges). Format currency columns with `#,##0`, date columns as dates.
   - Return `StreamingResponse` with `content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"` and `Content-Disposition: attachment; filename="{entity_type}_export.xlsx"`.

3. `templates/components/_grid.html`:
   - Add an "Export" button in the toolbar (next to page size selector or column selector).
   - Button is a plain `<a>` tag (not HTMX) pointing to `/views/export/{entity_type}?{current_query_string}`. Browser downloads the file natively.
   - Export button should use the same filter/column/sort query string that the grid currently has.

### 4B. Row-Level Export (Export Selected)

**Goal:** When rows are selected via checkboxes, the Export button should offer "Export All" vs "Export Selected" options.

**Changes needed:**
1. `templates/components/_grid.html`:
   - When bulk bar is visible (rows selected), add "Export Selected" button to the bulk action bar.
   - JS: `exportSelected()` builds URL with `record_ids=id1,id2,...` param and triggers download.

2. `routers/views.py`:
   - The export endpoint also accepts optional `record_ids` param. If provided, filter to just those IDs instead of running the full query.

## Key Files
- `echo2/templates/components/_grid.html` — add Export button to toolbar + Export Selected to bulk bar
- `echo2/routers/views.py` — add export endpoint
- `echo2/services/grid_service.py` — reuse `build_grid_context()` (no changes expected)
- `requirements.txt` — add openpyxl

## After Completing Phase 4
1. Update `Echo2/CLAUDE.md` — add session notes
2. Update `Echo2/feedback.md` — mark items `[x]`
3. Pause for context clear

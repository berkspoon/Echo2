# Echo 2.0 — Testing Feedback Log

## How to Use
Run the server: `cd echo2 && python -m uvicorn main:app --reload --port 8000`
Open: http://localhost:8000

Add feedback below as you test each module. Use the format:
```
- [ ] [Module] Issue description (severity: high/medium/low)
```

Mark fixed items with `[x]`.

---

## General / Layout
- [x] Sidebar menu and header (page name + search) must appear on ALL pages — some pages are missing them (severity: high) — **Fixed (round 2): Removed hx-boost="true" from body tag entirely. The HX-Boosted header check was unreliable — hx-boost was still intercepting navigations and returning partials. Without hx-boost, normal links do standard browser navigation (full page), while HTMX elements with explicit hx-get continue to work for partials. Simplified all router HX-Request checks by removing HX-Boosted logic.**
- [x] Clicking "Dashboard" in sidebar should navigate to the homepage (severity: medium) — **Already works: sidebar Dashboard link points to "/" which is the homepage.**
- [x] People and Organizations tabs should allow inline editing by clicking on the tab from the homepage (severity: medium) — **Fixed: Added Edit button column to both People and Organizations list tables.**
- [x] Sort/filter column headers, pagination page numbers, and "Next" button not clickable on list pages (severity: high) — **Fixed (round 2): Caused by hx-boost intercepting HTMX element clicks and adding HX-Boosted header, which made routers return full pages instead of partials into the wrong target. Removing hx-boost from body resolved this.**

## Organizations (/organizations/)
- [x] Cannot access individual organization detail page at all (severity: high) — **Fixed (round 2): Removed hx-boost entirely so org detail links do standard navigation and return full detail page.**
- [x] All columns should be sortable and filterable (severity: medium) — **Already had sort on all direct columns + filter dropdowns for relationship, type, country. Added Actions column.**
- [x] Former employees should show in their own tab (after "Fund Prospects" and "Fee Arrangements") (severity: medium) — **Fixed: Added "Former Employees" tab that filters people with link_type='former'. Created _tab_former_employees.html template.**

## People (/people/)
- [x] Clicking on a person sometimes goes to their linked organizations tab instead of the person detail page (severity: high) — **Fixed (round 2): Removed hx-boost so person detail links do standard navigation.**
- [x] All columns should be sortable and filterable (severity: medium) — **Fixed: Added sort on Phone column. All direct columns now sortable + filter dropdowns for asset class, DNC.**

## Activities (/activities/)
- [x] Clicking on a link from an activity does not go to the associated detail page (severity: high) — **Fixed (round 2): Removed hx-boost so activity detail links (org, person) do standard navigation to full detail pages.**
- [x] All columns should be sortable and filterable (severity: medium) — **Already had sort on date, title, type + filter dropdowns for type, author, date range.**

## Leads (/leads/)
- [x] All columns should be sortable and filterable (severity: medium) — **Fixed: Added sort on Service Type column. Also fixed Jinja2 `starts with` syntax error in stage badge (same bug as contracts).**

## Contracts (/contracts/)
- [x] 500 server error when clicking on individual contracts: `jinja2.exceptions.TemplateSyntaxError: expected token 'end of statement block', got 'starts'` (severity: high) — **Fixed: Changed `starts with` to `.startswith()` in contracts/detail.html line 138.**

## Fund Prospects (/fund-prospects/)
- [x] All columns should be sortable and filterable (severity: medium) — **Fixed: Added sort on Share Class column.**
- [x] Stage names should capitalize acronyms: "IC Review" (not "Ic Review") and "DDQ Materials Sent" (not "Ddq Materials Sent") (severity: low) — **Fixed: List table now uses stage_labels dict from reference_data instead of raw .title() filter.**

## Distribution Lists (/distribution-lists/)
- [x] Only "Official" distribution lists should be shown to everyone in the main table. Below that, a separate "My Distribution Lists" table for the user's custom lists (severity: medium) — **Fixed (round 2): Template was already split into two sections, but hx-boost was causing the page to render the _list_table.html partial (single table with all lists) instead of the full list.html (two-section layout). Removing hx-boost ensures standard navigation renders the full page with Official and My Lists sections.**

## Tasks (/tasks/my-tasks)

## Power User Feedback — Round 3 (March 13, 2026)

### Activities
- [x] [Activities] When linking an org, show that org's people for quick association; when linking a person, auto-add their primary org (severity: medium) — **Fixed (Session 12): HTMX org-people endpoint returns quick-add suggestion buttons; addPerson() auto-fetches and adds primary org chip**
- [x] [Activities] Add "My Activities" view showing user's own activities + activities for orgs/people where user is assigned coverage (severity: high) — **Fixed (Session 12): Multi-step coverage query (author + covered people + covered orgs). Toggle tabs in list.html**

### Tasks
- [x] [Tasks] Show suggested assignees (coverage owners) from linked activity's orgs when creating a task from an activity (severity: medium) — **Fixed (Session 12): Task form with ?linked_type=activity looks up coverage owners, shown as clickable chips**
- [x] [Activities] Make follow-up notes required when follow-up required is checked (severity: medium) — **Fixed (Session 12): Server-side validation in create/update + client-side required attribute toggle**
- [x] [Dashboard] Show follow-up notes on personal dashboard tasks widget (severity: low) — **Fixed (Session 12): Tasks widget includes notes+source, shows truncated follow-up notes for activity_follow_up tasks**

### Distribution Lists
- [x] [Distribution Lists] Add filters (country, client type, relationship type, fund) to member search on add-members page (severity: medium) — **Fixed (Session 12): search-people endpoint accepts country, rel_type, fund params. Filter dropdowns above search in _tab_members.html**

### My [Module] Views
- [x] [Organizations] Add "My Organizations" view filtered by user's coverage (severity: high) — **Fixed (Session 12): GET /organizations/my-organizations via coverage on people + leads. Toggle tabs + sidebar link**
- [x] [People] Add "My People" view filtered by coverage_owner (severity: high) — **Fixed (Session 12): GET /people/my-people filtered by coverage_owner**
- [x] [Fund Prospects] Add "My Fund Prospects" view filtered by aksia_owner (severity: high) — **Fixed (Session 12): GET /fund-prospects/my-fund-prospects filtered by aksia_owner_id**

### Dashboard
- [x] [Dashboard] Add "My Coverage Overview" widget showing counts of user's orgs/people/leads/fund prospects (severity: medium) — **Fixed (Session 12): 2x2 coverage grid widget with counts linking to "My" views**
- [x] [Dashboard] Add "Missing Info Alerts" widget for covered people/leads missing key fields (severity: medium) — **Fixed (Session 12): Top 5 people missing email/phone + leads missing revenue/service_type with edit links**
- [x] [Dashboard] Add "Stale Contacts" widget for covered people with no activity in 90+ days (severity: medium) — **Fixed (Session 12): Batched activity date lookup, sorted by staleness, primary org resolution**

## Final Feedback — Round 4 (March 15, 2026)

### Bugs
- [x] [General] Columns button dropdown is always visible on all module list pages — Alpine.js not loaded in base.html (severity: high) — **Fixed (Session 18): Added Alpine.js CDN to base.html + [x-cloak] CSS**
- [x] [People] Clicking on a person row navigates to `/persons/{id}` (404) instead of `/people/{id}` — generic onclick in _grid.html generates wrong URL (severity: high) — **Fixed (Session 18): Removed generic onclick that generated wrong URL; entity-specific links now work**
- [x] [Distribution Lists] Distribution list page shows "24 lists" but no rows render — no field_definitions seeded for distribution_list entity type (severity: high) — **Fixed (Session 18): Added DISTRIBUTION_LIST_FIELDS to seed_field_definitions.py**
- [x] [General] Required fields (e.g. company_name) should not be togglable off in the column selector. Exceptions: org can toggle relationship_type and organization_type, lead can toggle stage and share_class, task can toggle assigned_to and status (severity: medium) — **Fixed (Session 18): Required fields locked as checked+disabled in _column_selector.html with togglable exceptions**

### Enhancements
- [x] [Dashboards] Add customizable views with x-by-y variable selection (e.g. "pipeline by stage" vs "pipeline by fund") on Advisory Pipeline and Capital Raise dashboards. Clicking into a category should show a drilldown table of associated leads (severity: high) — **Fixed (Session 18): Group-by dropdowns + drilldown endpoints for both dashboards**
- [x] [Dashboards] Replace pipeline horizontal bars with vertical funnel flow charts (stacked trapezoids narrowing top-to-bottom) (severity: medium) — **Fixed (Session 18): CSS clip-path trapezoid shapes, reusable _funnel.html partial (later replaced with proportional-width bars in Session 19)**
- [x] [General] Redo filter functionality: add filter icon to each column header with sort (A-Z, Z-A) and data-type-appropriate filters (multi-select for dropdowns, contains/not-contains for text, inequality for numbers, before/after for dates). Remove existing filter dropdowns above grid, keep search box only (severity: high) — **Fixed (Session 18): Per-column filter icons with type-aware dropdowns. cf_<field>=<op>:<value> URL format. Old filter dropdowns removed**
- [x] [General] Rename "Saved Views" to "Screeners". Add ability to name, save, overwrite, duplicate, and delete screeners. Clicking a screener loads its saved columns and filters (severity: high) — **Fixed (Session 18): Full screener CRUD — save, overwrite, duplicate, rename, delete. Hover-revealed action buttons**

## Patrick Feedback — Round 5 (March 16, 2026)

**Stakeholder:** padelsbach@aksia.com
**Source files:** `Patrick feedback 2.md` (AI summary), `Patrick 2.vtt` (transcript)
**Verified:** AI summary verified against raw transcript. One inaccuracy found (multi-tenant mislabeled as "Phase 1" — Patrick explicitly said "Not Phase 1").

### Field Architecture
- [x] [Admin] Custom EAV fields don't appear in entity edit forms — only in grids. Must render in forms too (severity: high) — **Fixed: Added dynamic EAV section to all 5 entity form templates + split_core_eav() for proper DB save**
- [x] [Admin] Remove section assignment from field definitions. Sections should only exist at the layout level, not hardcoded into fields. Create default layouts from current sections (severity: medium) — **Fixed: page_layouts now authoritative via _group_fields_by_layout_or_fallback(). seed_default_layouts.py created.**
- [x] [Admin] Merge Reference Data management into the Fields page. Dropdown/multi-select fields should show inline value editor. Remove separate Reference Data admin page (severity: high) — **Fixed: Inline dropdown value management via HTMX endpoints. _inline_reference_data.html. Sidebar link removed.**
- [x] [Admin] Add visibility rules admin UI to field editor — currently only configurable via seed scripts (severity: medium) — **Fixed: Visibility conditions editor in field_form.html with when/equals/in/not_in/min_stage/lead_type**
- [x] [Admin] Add "suggested" field concept — fields highlighted with amber when conditions are met, non-blocking. Keep required fields static to avoid screener complications (severity: medium) — **Fixed: suggestion_rules JSONB, _is_field_suggested(), amber border+badge in _field_renderer.html**
- [x] [Admin] Add "text_list" field type for storing multiple text strings (nicknames/aliases). All values searchable. Use case: org abbreviations like OCERS, OC ERS, Orange County (severity: medium) — **Fixed: Alpine.js multi-input, JSON storage in EAV, grid comma display, seeded nicknames field**

### Grid Enhancements
- [x] [Grid] Add cross-entity linked columns: org fields (city, country, type, AUM) on People and Leads grids; aggregate columns (contact count) on Org grid (severity: high) — **Fixed: 9 new virtual columns across org/person/lead entities**
- [x] [Grid] Add "Has Active Leads" boolean filter on Org and People grids. Active = rating NOT IN won/lost stages (severity: medium) — **Fixed: has_active_leads virtual boolean with pre-filter in _execute_query**
- [x] [Grid] Add column resizing via draggable borders. Persist widths in screeners and localStorage (severity: medium) — **Fixed: CSS resize handles, JS drag handler, localStorage persistence**
- [x] [Grid] Add pop-up row editor — edit button opens modal with fields for visible columns only. Save inline without page navigation (severity: high) — **Fixed: _grid_edit_modal.html, grid-edit endpoints in views.py, gridRefresh event**

### Dashboards
- [x] [Dashboards] Pipeline should default to showing all leads (not just "Active Leads"). Add explicit active/inactive toggle filter. Add stage to top filter bar (severity: medium) — **Fixed: active_filter + stage params, "Active Leads" renamed to "Leads"**
- [x] [Dashboards] Dynamic pipeline grouping — auto-populate group-by dropdown from all dropdown/multi-select fields in field_definitions, including custom fields (severity: medium) — **Fixed: _get_groupable_fields() from field_definitions**
- [x] [Dashboards] Replace static drill-down tables with full grid component. Pre-apply dashboard filters. Support column selection, sorting, filtering within drilldown (severity: high) — **Fixed: Both advisory+capital raise drilldowns use build_grid_context() with grid_container_id_override**

### Distribution Lists
- [x] [Distribution Lists] Add dynamic distribution lists — store filter criteria, auto-resolve membership from filters. Static snapshots with manual additions. Snapshot on send (severity: high) — **Fixed: list_mode/filter_criteria columns, _resolve_dynamic_members(), updated _build_send_preview()**
- [x] [Distribution Lists] Create/edit dynamic list via embedded people grid with full filter capabilities. Save filters as list criteria (severity: medium) — **Fixed: filter-editor/filter-grid/save-filters endpoints, _filter_editor.html**
- [x] [Distribution Lists] Show current members in real-time when adding new people (auto-refresh via HTMX trigger) (severity: low) — **Fixed: HX-Trigger: membersUpdated + hx-trigger listener on members-content**

### Screeners & Navigation
- [x] [Grid] Split screener dropdown into "My Screeners" and "Team Screeners" sections. Team screeners show shared views from other users with Duplicate action only (severity: low) — **Fixed: Split in _grid.html with owner name enrichment in grid_service.py**
- [x] [Navigation] Remove Reference Data from admin sidebar. Merge Pipeline section into Records. Simplify sidebar groupings (severity: low) — **Fixed: base.html sidebar restructured**

### Deferred Items (not implementing now)
- Multi-tenant architecture — Patrick: "Not Phase 1." Defer entirely.
- Generic admin-configurable calculated fields — Implement specific virtual columns instead.
- Duplicate detection merge functionality — Patrick: "We'll take a look once worked out."
- Editable Excel-style grid — Pop-up editor covers the use case per Patrick.

### Post-Implementation Bug Fixes (March 22, 2026)
- [x] [Distribution Lists] 500 error on distribution lists page — `list_mode` column didn't exist. Root cause: DB migration not applied. Fixed by running migrate_schema.sql in Supabase SQL Editor.
- [x] [Grid] "Has Active Leads" filter showing people without active leads — `_extract_column_filters()` keeps `cf_` prefix but pre-filter checked for key without prefix. Fixed key to `cf_has_active_leads`.
- [x] [Fields] text_list (nicknames) values don't persist — Alpine.js `x-data` attribute used double quotes which broke JSON array parsing. Fixed to single-quoted attribute.
- [x] [Forms] Custom EAV fields appeared in generic bottom section — Updated all 5 entity form templates to render EAV fields in their correct section with "(custom)" label. Unknown sections grouped under "Additional Custom Information".
- [x] [Admin] Manage Values stuck in "Loading..." — Stale uvicorn process from before code changes was serving old code. Fixed by killing all Python processes and restarting.
- [ ] [Admin] Visibility conditions UI should use dropdowns instead of text inputs for field selection and value selection (severity: low) — deferred to polish pass

## Session 21 Testing — March 26, 2026

### Bug Fixes
- [x] [Has Active Leads] Filter works for both Orgs and People — server logs confirmed requests returning 200 with filtered results. Grid updates behind the dropdown.
- [x] [Distribution Lists] Filter editor 500 error — `merged_filters` undefined in `_filter_editor.html`. Fixed by computing and passing in endpoint.
- [x] [Distribution Lists] Dynamic list preview/send — `_resolve_dynamic_members` crashed on org-level virtual filters; `_build_send_preview` had N+1 queries. Both fixed.
- [x] [Dashboards] Drill-down column selector refreshed whole dashboard page — `applyColumns()` used `window.location` instead of drill-down `base_url`. Fixed.

### Enhancements
- [x] [Admin] Dropdown values now manageable from individual field edit page (not just field list)
- [x] [Admin] Section assignment dropdown in field editor (populated from page_layouts + field_definitions)
- [x] [Dashboards] Drill-down grids no longer show column filter icons (per Patrick feedback)
- [x] [Distribution Lists] Dynamic vs static member display split — "Dynamic Members" (blue) and "Manual Additions" (amber) sections
- [x] [Grid] Linked org columns (org_city, org_country, org_type, org_aum_mn) now filterable on People and Leads grids
- [x] [Admin] Linked/calculated field type — admin-configurable `storage_type='linked'` with source entity/field/relationship dropdowns
- [x] [Admin] Linked field source field is now a dropdown (not text input); "Direct FK" renamed to "Direct reference" with help text

## Josh Feedback — Round 6 (March 26, 2026)

**Stakeholder:** Josh (power user)

### Bugs
- [x] [Dashboards] Applying additional columns to dashboard drill-down table shows "no records found" — drilldown endpoint returned full wrapper template on grid reload, causing nested HTML. Fixed by detecting grid-internal reloads and returning just the grid partial (severity: high)
- [x] [Distribution Lists] Dynamic filter form automatically adds everyone — empty filter criteria `{}` saved when no column filters applied, matching all non-DNC people. Fixed with server-side validation requiring at least one `cf_*` filter and UI warning (severity: high)

### Enhancements
- [x] [Grid] Bulk add/select/update — row checkboxes, select all, floating bulk action bar with "Edit Selected" and "Delete Selected" (severity: high) — **Fixed: Checkboxes on each grid row + select-all header checkbox (hidden on drilldown grids). Floating bulk action bar with count, Edit Selected, Delete Selected, Clear. Bulk edit modal with field selector (type-aware value input). POST /views/bulk-edit/{entity_type} with core+EAV support and audit logging. POST /views/bulk-delete/{entity_type} (admin only, soft delete with audit). All grid entities supported.**
- [x] [Dashboards] Advisory pipeline analysis bar should reflect lead count, not expected revenue amount — add metric selector (count/revenue/FLAR) (severity: medium) — **Fixed: Added metric selector (Lead Count / Expected Revenue / Yr1 FLAR) next to group-by. Bar sizing and labels change by metric. Metric param passed through chart and drilldown endpoints.**
- [x] [Dashboards] Separate focus-rated dashboard view — implement as saved dashboard preset with stage=focus filter (severity: medium) — **Fixed: Dashboard presets system using saved_views table with entity_type='dashboard_advisory'. Save Preset button captures current filter state. Presets shown as link buttons above filter bar. Reuses existing POST /views/save endpoint.**
- [x] [Dashboards] Capital raise: analysis by country — add "Country" as group-by dimension on capital raise chart (severity: medium) — **Fixed: Added "Country" option to capital raise group-by dropdown. Resolves org country via batch_resolve_orgs(). Country labels from reference_data. Drilldown filtering by country supported.**
- [x] [Dashboards] Capital raise: filter by owner for personal pipeline view (severity: medium) — **Fixed: Added owner dropdown to capital raise dashboard with "My Pipeline" option. Owner filter applied at DB query level. Persists across fund tab switches, chart, and drilldown.**
- [x] [Dashboards] Capital raise: highlight organizations with most traction — "Hot Prospects" section with traction scoring based on stage advancement (severity: medium) — **Fixed: Traction scoring (0-5) by stage. Hot Prospects table shows orgs with score >= 3. Green badge for score 5 (soft circle+), amber for 3-4 (DD/IC review). Grouped by org with highest stage, fund tickers, total allocation.**
- [x] [General] Enable exporting of data to Excel — add Export button to grid toolbar generating .xlsx (severity: high) — **Fixed: Export button in grid toolbar downloads .xlsx via GET /views/export/{entity_type}. Respects current filters, column selection, and sort order. Uses openpyxl with type-aware formatting (currency #,##0, dates as dates, booleans Yes/No, dropdowns title-cased). Enriched display values (org names, owner names, fund tickers) instead of raw UUIDs. Auto-sized columns. Export Selected button in bulk action bar exports only checked rows via record_ids param. export_mode flag on build_grid_context bypasses page_size cap.**

### Testing Round 2 — Bug Fixes (March 26, 2026)
- [x] [Dashboards] Presets endpoint 500 — `TypeError: 'list' object is not a mapping`. Columns field in saved_views can be a list (grid screeners) or dict (dashboard presets). Fixed with `isinstance(columns, dict)` guard (severity: high)
- [x] [Dashboards] Drilldown URL double-`?` — `base_url` for drilldowns contains `?` but grid template appended another `?`. Fixed with `url_sep` variable that uses `&` when `base_url` already has `?` (severity: high)
- [x] [Dashboards] Drilldown column change still shows "no records found" — `{{ base_url }}` in column selector JS string was HTML-escaped by Jinja2 (`&` → `&amp;`), corrupting the URL. Fixed with `{{ base_url | safe }}` (severity: high)
- [x] [Dashboards] Advisory metric default was "revenue", changed to "count" per Josh feedback. Non-stage group-bys now sort descending by selected metric (severity: medium)
- [x] [Dashboards] Top filter change resets metric/group_by — hidden inputs for metric/group_by added to filter form; chart dropdowns sync values to hidden inputs via onchange. Added `group_by` parameter to main advisory pipeline endpoint (severity: medium)
- [x] [Grid] Bulk edit `coverage_owner` sends display name instead of UUID — `lookup` fields fell through to text input. Added `lookup` case rendering user select dropdown with UUID values. Users list embedded as `window._bulkEditUsers` (severity: high)
- [x] [Grid] Bulk edit dropdown fields show empty "New Value" — `dropdown_category` not set on some field_definitions. Added fallback in `enrich_field_definitions` to try `field_name` as reference_data category (severity: medium)
- [x] [Dashboards] Added delete buttons (red X on hover) for own presets (severity: low)
- [x] [Distribution Lists] Column selector Apply in filter editor navigates away from filter editor — needs redesign toward filter-builder UX (select criteria to include people) rather than grid-distill approach (severity: high) — **Fixed: Complete rewrite to filter-BUILDER UX. Each row: field dropdown + operator dropdown + value input (type-aware). Live preview count via HTMX. New filter format: `{"filters": [...]}` with backward-compat for old `cf_*` format. `_resolve_dynamic_members` handles both formats.**
- [x] [Dashboards] Capital raise: default to active leads (exclude closed/declined), sort by raise amount, add lead_type sort. Hot prospects: remove Funds column, add Lead Owner, add owner/stage filters (severity: medium) — **Fixed: Active filter (default excludes closed+declined) added to all capital raise endpoints with Status dropdown. Sort by allocation already correct. Hot prospects: removed Fund(s) column, added Lead Owner (resolved via batch_resolve_users), added client-side JS owner/stage filter dropdowns.**

## Seed Data Issues

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
- [ ] [Activities] When linking an org, show that org's people for quick association; when linking a person, auto-add their primary org (severity: medium)
- [ ] [Activities] Add "My Activities" view showing user's own activities + activities for orgs/people where user is assigned coverage (severity: high)

### Tasks
- [ ] [Tasks] Show suggested assignees (coverage owners) from linked activity's orgs when creating a task from an activity (severity: medium)
- [ ] [Activities] Make follow-up notes required when follow-up required is checked (severity: medium)
- [ ] [Dashboard] Show follow-up notes on personal dashboard tasks widget (severity: low)

### Distribution Lists
- [ ] [Distribution Lists] Add filters (country, client type, relationship type, fund) to member search on add-members page (severity: medium)

### My [Module] Views
- [ ] [Organizations] Add "My Organizations" view filtered by user's coverage (severity: high)
- [ ] [People] Add "My People" view filtered by coverage_owner (severity: high)
- [ ] [Fund Prospects] Add "My Fund Prospects" view filtered by aksia_owner (severity: high)

### Dashboard
- [ ] [Dashboard] Add "My Coverage Overview" widget showing counts of user's orgs/people/leads/fund prospects (severity: medium)
- [ ] [Dashboard] Add "Missing Info Alerts" widget for covered people/leads missing key fields (severity: medium)
- [ ] [Dashboard] Add "Stale Contacts" widget for covered people with no activity in 90+ days (severity: medium)

## Final Feedback — Round 4 (March 15, 2026)

### Bugs
- [ ] [General] Columns button dropdown is always visible on all module list pages — Alpine.js not loaded in base.html (severity: high)
- [ ] [People] Clicking on a person row navigates to `/persons/{id}` (404) instead of `/people/{id}` — generic onclick in _grid.html generates wrong URL (severity: high)
- [ ] [Distribution Lists] Distribution list page shows "24 lists" but no rows render — no field_definitions seeded for distribution_list entity type (severity: high)
- [ ] [General] Required fields (e.g. company_name) should not be togglable off in the column selector. Exceptions: org can toggle relationship_type and organization_type, lead can toggle stage and share_class, task can toggle assigned_to and status (severity: medium)

### Enhancements
- [ ] [Dashboards] Add customizable views with x-by-y variable selection (e.g. "pipeline by stage" vs "pipeline by fund") on Advisory Pipeline and Capital Raise dashboards. Clicking into a category should show a drilldown table of associated leads (severity: high)
- [ ] [Dashboards] Replace pipeline horizontal bars with vertical funnel flow charts (stacked trapezoids narrowing top-to-bottom) (severity: medium)
- [ ] [General] Redo filter functionality: add filter icon to each column header with sort (A-Z, Z-A) and data-type-appropriate filters (multi-select for dropdowns, contains/not-contains for text, inequality for numbers, before/after for dates). Remove existing filter dropdowns above grid, keep search box only (severity: high)
- [ ] [General] Rename "Saved Views" to "Screeners". Add ability to name, save, overwrite, duplicate, and delete screeners. Clicking a screener loads its saved columns and filters (severity: high)

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

## Seed Data Issues

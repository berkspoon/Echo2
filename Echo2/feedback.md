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
- [x] Sidebar menu and header (page name + search) must appear on ALL pages — some pages are missing them (severity: high) — **Fixed: hx-boost was causing all navigations to return HTMX partials instead of full pages. Added HX-Boosted header check to all 10 router list/detail endpoints.**
- [x] Clicking "Dashboard" in sidebar should navigate to the homepage (severity: medium) — **Already works: sidebar Dashboard link points to "/" which is the homepage.**
- [x] People and Organizations tabs should allow inline editing by clicking on the tab from the homepage (severity: medium) — **Fixed: Added Edit button column to both People and Organizations list tables.**

## Organizations (/organizations/)
- [x] Cannot access individual organization detail page at all (severity: high) — **Fixed: hx-boost was returning the People tab partial instead of the full detail page. Added HX-Boosted check.**
- [x] All columns should be sortable and filterable (severity: medium) — **Already had sort on all direct columns + filter dropdowns for relationship, type, country. Added Actions column.**
- [x] Former employees should show in their own tab (after "Fund Prospects" and "Fee Arrangements") (severity: medium) — **Fixed: Added "Former Employees" tab that filters people with link_type='former'. Created _tab_former_employees.html template.**

## People (/people/)
- [x] Clicking on a person sometimes goes to their linked organizations tab instead of the person detail page (severity: high) — **Fixed: hx-boost was returning the Organizations tab partial. Added HX-Boosted check so full detail page is returned for page navigations.**
- [x] All columns should be sortable and filterable (severity: medium) — **Fixed: Added sort on Phone column. All direct columns now sortable + filter dropdowns for asset class, DNC.**

## Activities (/activities/)
- [x] Clicking on a link from an activity does not go to the associated detail page (severity: high) — **Fixed: hx-boost was intercepting link clicks and returning partials. Added HX-Boosted check to all endpoints.**
- [x] All columns should be sortable and filterable (severity: medium) — **Already had sort on date, title, type + filter dropdowns for type, author, date range.**

## Leads (/leads/)
- [x] All columns should be sortable and filterable (severity: medium) — **Fixed: Added sort on Service Type column. Also fixed Jinja2 `starts with` syntax error in stage badge (same bug as contracts).**

## Contracts (/contracts/)
- [x] 500 server error when clicking on individual contracts: `jinja2.exceptions.TemplateSyntaxError: expected token 'end of statement block', got 'starts'` (severity: high) — **Fixed: Changed `starts with` to `.startswith()` in contracts/detail.html line 138.**

## Fund Prospects (/fund-prospects/)
- [x] All columns should be sortable and filterable (severity: medium) — **Fixed: Added sort on Share Class column.**
- [x] Stage names should capitalize acronyms: "IC Review" (not "Ic Review") and "DDQ Materials Sent" (not "Ddq Materials Sent") (severity: low) — **Fixed: List table now uses stage_labels dict from reference_data instead of raw .title() filter.**

## Distribution Lists (/distribution-lists/)
- [x] Only "Official" distribution lists should be shown to everyone in the main table. Below that, a separate "My Distribution Lists" table for the user's custom lists (severity: medium) — **Fixed: Split list page into two sections — "Official Distribution Lists" and "My Distribution Lists". Router now passes both official_lists and my_lists to template.**

## Tasks (/tasks/my-tasks)

## Seed Data Issues

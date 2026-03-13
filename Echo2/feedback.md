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

## Seed Data Issues

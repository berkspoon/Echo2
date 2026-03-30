# Continuation Prompt for Next Session

Copy and paste this as your first message:

---

We are continuing work on Echo 2.0 data import and Lead V17 implementation. Read these files to get full context:

1. `@CLAUDE.md` — project overview and coding standards
2. `@DATA_IMPORT_PLAN.md` — the comprehensive plan with all decisions, field mappings, implementation steps, and **file reference guide** for schema changes
3. `@feedback.md` — testing feedback history

**Where we left off:** Steps 1, 2, 3A, and 3B are COMPLETE. Code changes committed. Migration SQL needs to be run against Supabase for Phase 9 (person_coverage_owners junction table).

**What was done in Step 2 (Fundraise → Product Cleanup):**
- Renamed all `fundraise` references to `product` across ~15 files
- schema.sql: updated lead_stage parent_values (advisory→service, fundraise→product), removed lead_type='fundraise'
- seed_data.py: renamed seed_fundraise_leads() → seed_product_leads(), changed lead_type to 'product'
- Template renamed: _tab_fundraise_leads.html → _tab_product_leads.html
- All variables renamed: is_fundraise→is_product, section-fundraise→section-product, fundraise_leads→product_leads
- Labels updated: "Fundraise Lead Next Steps" → "Product Lead Next Steps"
- distribution_lists.py: fund-based DL queries now check leads table (lead_type='product') in addition to legacy fund_prospects

**What was done in Step 3B (Prospect→Client Workflow):**
- Added `_transition_prospect_to_client()` helper in leads.py
- When a lead's rating is set to "won", if the linked org is a "prospect", it auto-transitions to "client" with audit logging
- Added 5 `client_team_coverage` EAV lookup fields to org field_definitions (visible + suggested when relationship_type='client')
- Logic fires on both lead create and update (won rating)

**What was done in Step 3A (Multi-Coverage Junction Table):**
- New `person_coverage_owners` table (Phase 9 migration SQL) with person_id, user_id, is_primary
- Data migration from existing coverage_owner column to junction table
- Dual-write: _sync_coverage_owners() updates both junction table AND legacy coverage_owner column
- People form: typeahead autocomplete (HTMX /people/search-users) with chip UI for multi-select
- People detail: coverage owners displayed as chips with primary badge
- Grid: people enrichment resolves coverage owners from junction table
- Dashboard: my-coverage widget, missing-info, stale-contacts all query junction table
- Org detail: coverage rollup uses junction table
- Activities: "My Activities" uses junction table for coverage filter
- Tasks: suggested assignees use junction table
- Quick-create person in activities creates junction table entry
- Seed data: seed_person_coverage_owners() creates primary + 25% secondary coverage owners

**Migration SQL to run on Supabase:**
```sql
-- Phase 9 from echo2/db/migrate_schema.sql
-- Creates person_coverage_owners table + migrates existing coverage_owner data
```

**Known issue:** Windows zombie Python processes — always use a fresh port (8002+) when testing locally.

**What to work on next:**
- **Test Steps 2, 3A, 3B** — Run migration SQL, re-seed field definitions, test locally
- **Step 0: Create Users** — BLOCKED on active employee list from Miles.
- **Steps 4-7: Data Import** — BLOCKED on Step 0.
- **Step 2.5 (deferred): Dynamic Lead Form** — Refactor 930-line hardcoded lead form to render from field_definitions. 80% infrastructure ready. 5 custom widgets need extraction.

**Custom skill available:** `/spec-feature` — use this to interactively spec out new modules.

---

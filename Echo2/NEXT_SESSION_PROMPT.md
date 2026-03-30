# Continuation Prompt for Next Session

Copy and paste this as your first message:

---

We are continuing work on Echo 2.0 data import and Lead V17 implementation. Read these files to get full context:

1. `@CLAUDE.md` — project overview and coding standards
2. `@DATA_IMPORT_PLAN.md` — the comprehensive plan with all decisions, field mappings, implementation steps, and **file reference guide** for schema changes
3. `@feedback.md` — testing feedback history

**Where we left off:** Step 1 (Lead Schema + V17 Fields) is COMPLETE and deployed. Migration SQL has been run against Supabase. Field definitions re-seeded. All 16 files updated. Tested and working on localhost.

**What was done in Step 1:**
- 29 new columns on leads table, 10 new reference_data categories
- Renamed: lead_type advisory→service, fundraise→product; 3 lost stages → did_not_win; relationship/service_type/risk_weight values
- 58 field definitions across 13 sections (up from 34)
- Form template updated with all V17 sections (Engagement Status, Coverage Office, Overview, IM Details, Product Details, RFP, Timeline, Closure with decline fields)
- Removed from UI: pricing_proposal, expected_revenue, expected_decision_date, rfp_status
- Engagement status auto-populates timeline dates
- All routers + templates updated for new values

**Known issue:** Windows zombie Python processes — always use a fresh port (8002+) when testing locally. Old processes on port 8000/8001 serve stale code.

**Pending design decision:** Lead form template is hardcoded HTML (~800 lines). Should be refactored to render dynamically from field_definitions (form_service.py + _field_renderer.html already support this). Only 4-5 complex widgets need custom HTML. This would make future field changes database-only. Consider as Step 2.5.

**What to work on next:**
- **Step 2: Fundraise → Product Merger + Dashboard Updates** — Most of this was already done in Step 1 (all fundraise→product renames complete). Review what's left: Capital Raise dashboard may need product-specific adjustments, grid_service product lead queries.
- **Step 3: Multi-Coverage + Prospect→Client Workflow** — New person_coverage_owners junction table, update people forms/grids, build prospect→client transition on lead won.
- **Step 0: Create Users** — BLOCKED on active employee list from Miles.
- **Steps 4-7: Data Import** — BLOCKED on Step 0.

**Custom skill available:** `/spec-feature` — use this to interactively spec out new modules.

---

# Echo 2.0 — Data Import & Lead V17 Implementation Plan

**Created:** March 29, 2026
**Updated:** March 30, 2026
**Status:** Steps 0-7 ALL COMPLETE. Full CRM data import and validation done.

---

## Overview

Two parallel workstreams:
1. **Lead V17 Field Updates** — Add ~25 new fields, restructure stages/relationships/asset classes per Patrick's V17 spec
2. **CRM Data Import** — Import real data from Power Apps Echo (5.3K orgs, 12.9K people, 2.5K leads, 404 contracts, 27.4K activities)

Lead schema changes come FIRST so imported data lands in the right columns.

---

## Key Decisions (Confirmed March 29, 2026)

| Decision | Details |
|----------|---------|
| Lead types | Two types: **"service"** (advisory, IM, research, reporting, project) and **"product"**. Rename `lead_type` from advisory/fundraise/product to service/product. |
| Fundraise merge | Fundraise leads merge into product. Fund-specific fields visible when `lead_type='product'`. |
| V17 scope | All ~25 new fields implemented now, before data import. |
| Next Steps | KEEP both next_steps and next_steps_date. Rename concept to "follow-up". Preserve auto-task generation. |
| Pricing Proposal | Remove from UI. Engagement Status replaces it. |
| Expected Revenue | Replace with expected_fee (service-type-specific). Dashboard metrics switch to expected_fee. |
| RFP Status | Convert to auto-populated boolean: Y if engagement_status in (rfp_expected, rfp_in_progress). |
| Rating stages | V17 version: merge 3 lost types → "did_not_win" + decline_reason_code |
| Risk Weight | Change to percentage ranges (0-25%, 25-50%, 50-75%, 75-100%) |
| Relationship | Rename: new→new_client, cross_sell→existing_client_new_business, contract_extension→existing_client_contract_extension, add platform_relationship_approval |
| Multi-owner leads | Keep lead_owners junction table |
| Multi-coverage people | Change coverage_owner from single FK to junction table (like lead_owners). All org coverage users → all linked people |
| Client team coverage | When lead won + org transitions prospect→client, "client team coverage" 1-5 become suggested fields. Build prospect→client transition workflow. |
| Dual-nature leads | Leads CAN be both product and service. Add boolean flags (includes_product_allocation / includes_max_access) rather than multi-select lead_type. |
| HF asset class | Drop "Primaries" for Hedge Funds — just "Hedge Funds" |
| Asset class approach | Option B: parent_value scoping in reference_data (matches existing lead_stage pattern) |
| IM allocation % | Dynamic: show "% of [asset class]" for each selected asset class when multiple selected |
| Service type subtypes | Add as non-required field based on service_type (from Harry's sheet) |
| Activities import | Full import (not stubs) — 27.4K activities with titles, descriptions, dates, authors from CSV |
| Users | Generate emails as [firstinitial][lastname]@aksia.com from display names |
| Publication subscriptions | 0/blank = not in system, 1 = none (not subscribed), 2 = L2. **L1 status not found — Miles investigating** |
| "Approved by Client" | Not a valid engagement status for now |
| Date Committed/Declined | Confirmed removal |
| L1/L2 superset | Same behavior — L2 includes all L1 material |
| Hot Prospects | Still important for products |

---

## Data Source Files

| File | Location | Size | Contents |
|------|----------|------|----------|
| EchoData.xlsx | `Echo2/EchoData.xlsx` | — | 5 sheets: Organizations (5,383), People (12,912), Contracts (404), Leads (2,456), ActivityEntities (76,964 link rows) |
| cr932_crmactivities.csv | `Echo2/cr932_crmactivities.csv` | 258MB | 27,373 activity records with title, type, author, date, HTML+plaintext descriptions, linked org/people names |
| Lead Fields Page V17.xlsx | `Echo2/Lead Fields Page V17.xlsx` | — | 11 sheets: field specs, UI views, field values, screener view, Harry's lead logic |

---

## Numeric ID → Text Mappings (ALL COMPLETE as of March 30, 2026)

### Organization Entity Types
| ID | Echo 2.0 Value |
|----|---------------|
| 1 | private_pension |
| 2 | financial_institution |
| 3 | endowment_foundation |
| 4 | insurance_company |
| 5 | sovereign_wealth_fund |
| 6 | public_pension |
| 7 | other |
| 8 | government |
| 9 | supranational |
| 10 | superannuation_fund |
| 11 | asset_manager_gp |
| 12 | family_office |
| 13 | private_bank |
| 14 | retail_platform |
| 15 | healthcare_organization |
| 16 | wealth_manager_ria |
| 17 | conference_publication |
| 19 | placement_agent |
| 20 | private_pension_taft_hartley |
| 22 | consultant_ocio |

**Note:** Need to add 12 new organization_type values to reference_data.

### Organization Relationship Types
| ID | Echo 2.0 Value |
|----|---------------|
| 0 | prospect |
| 1 | client |
| 2 | other |

### Coverage Office
| ID | Echo 2.0 Value |
|----|---------------|
| 1 | us |
| 2 | emea |
| 3 | tokyo |
| 4 | hk |

### Engagement Status
| ID | Echo 2.0 Value |
|----|---------------|
| 1 | not_yet_contacted |
| 2 | prospect_contacted |
| 3 | prospect_responded |
| 4 | initial_meeting |
| 5 | ongoing_dialogue |
| 6 | pricing_proposal_submitted |

**Note:** V17 adds 4 more values not in CRM data: rfp_expected, rfp_in_progress, rfp_submitted, approved_by_client.

### Service Type
| ID | Echo 2.0 Value |
|----|---------------|
| 1 | investment_management |
| 2 | advisory |
| 3 | research |
| 4 | reporting |
| 5 | product |
| 6 | project |
| 7 | advisory_bps |

**Note:** ID=7 (Advisory BPS) is new — not in current Echo 2.0 reference_data. Need to add.

### Lead Status / Rating
| ID | Echo 2.0 Value |
|----|---------------|
| 1 | exploratory |
| 2 | radar |
| 3 | focus |
| 4 | verbal_mandate |
| 5 | won |
| 10 | did_not_win |

### Relationship
| ID | Echo 2.0 Value |
|----|---------------|
| 1 | new_client |
| 3 | existing_client_contract_extension |
| 5 | (unknown — only on "Test" lead, likely junk) |
| 6 | existing_client_new_business |

### RFP Status
| ID | Echo 2.0 Value |
|----|---------------|
| 1 | submitted |
| 2 | in_progress |
| 3 | expected |
| 4 | not_applicable |

### Pricing Proposal (REMOVED from CRM — historical data only)
| ID | Echo 2.0 Value |
|----|---------------|
| 1 | formal |
| 2 | informal |
| 3 | no_proposal |

### Risk Weight / Probability of Close
| ID | Echo 2.0 Value |
|----|---------------|
| 0 | 0_25 |
| 1 | 25_50 |
| 2 | 50_75 |
| 3 | 75_100 |

**Note:** Has a `0` value we hadn't seen in initial data scan. 4 values total, not 3.

### Waystone Approved
| ID | Echo 2.0 Value |
|----|---------------|
| 1 | yes |
| 2 | no |
| 3 | not_applicable |

### Commitment Status (REMOVED from CRM — historical data only)
| ID | Echo 2.0 Value |
|----|---------------|
| 1 | initial_review |
| 2 | in_diligence |
| 3 | ic_approved |
| 4 | on_hold |
| 5 | legal_approved |

**Note:** Inferred from V17 spec ordering. Field removed from CRM in latest update; data exists for backfill only.

### Activity Type
| ID | Echo 2.0 Value |
|----|---------------|
| 1 | call |
| 2 | meeting |
| 3 | note |
| 4 | email |

### Publication Subscriptions
| ID | Echo 2.0 Value |
|----|---------------|
| 1 | none |
| 2 | l2 |
| 3 | unsubscribed |
| 4 | l1 |
| 5 | l1_unsubscribed_from_l2 |

**Import logic:** Value=2 → L2 member. Value=4 → L1 member. Value=5 → L1 member (was L2, downgraded). Values 1, 3 → skip.

### Countries (84 distinct values — needs normalization)
Source: Echo Mappings.xlsx "CountriesDistinctList" sheet. Includes duplicates (US/USA/United States/United States of America), cities as countries (Dubai, Mumbai, Shanghai, Karlsruhe, Hannover, Amsterdam, Abu Dhabi, Copenhagen), and variant spellings (Untied States, Columbia vs Colombia, England vs United Kingdom vs UK). Country normalization mapping will be built in the import script.
---

## V17 New Fields Summary

### Fields to ADD (all lead types unless noted):

| Field | Type | Section | Visibility | Priority |
|-------|------|---------|-----------|----------|
| engagement_status | dropdown (10 values) | Headline | Always | Critical |
| commitment_status | dropdown (5 values) | IM/Product | service_type=product AND rating>=focus | Critical |
| waystone_approved | dropdown (3 values) | Product | service_type=product | Critical |
| decline_reason_code | dropdown (11 values) | Declined | rating=did_not_win | Critical |
| decline_rationale | textarea (500 chars) | Declined | rating=did_not_win | Critical |
| indicative_size_low | currency | Focus | service_type in (product, IM) AND rating>=focus | High |
| indicative_size_high | currency | Focus | service_type in (product, IM) AND rating>=focus | High |
| coverage_office | dropdown (4 values) | Overview | Always | High |
| prospect_contacted_date | date (auto) | Timeline | Auto when engagement_status reaches prospect_contacted | High |
| prospect_responded_date | date (auto) | Timeline | Auto when engagement_status reaches prospect_responded | High |
| initial_meeting_date | date (auto) | Timeline | Auto when engagement_status reaches initial_meeting | High |
| initial_meeting_complete_date | date (auto) | Timeline | Auto when engagement_status reaches ongoing_dialogue | High |
| revenue_currency | dropdown | Focus | rating>=focus | Medium |
| expected_management_fee | number(%) | IM Details | service_type=IM AND rating>=focus | Medium |
| expected_incentive_fee | number(%) | IM Details | service_type=IM AND rating>=focus | Medium |
| expected_preferred_return | number(%) | IM Details | service_type=IM AND rating>=focus | Medium |
| expected_catchup_pct | number(%) | IM Details | service_type=IM AND rating>=focus | Medium |
| expected_size | text (50 chars) | IM/Product Details | service_type in (IM, product) AND rating>=focus | Medium |
| expected_fee | currency | Service Details | service_type in (advisory, research, project, reporting) AND rating>=focus | Medium |
| gp_commitment | dropdown (yes/no) | IM Details | service_type=IM | Medium |
| deployment_period | dropdown | IM Details | service_type=IM | Medium |
| expected_contract_start_date | date | Details | rating>=focus | Medium |
| expected_fund_close | dropdown | Product Details | service_type=product AND rating>=focus | Medium |
| rfp_due_date | date | RFP | engagement_status=rfp_in_progress | Medium |
| rfp_submitted_date | date | RFP | engagement_status=rfp_submitted | Medium |
| service_subtype | dropdown | Overview | Based on service_type (Harry's sheet) | Low |
| includes_product_allocation | boolean | Overview | lead_type=service | Low |
| includes_max_access | boolean | Overview | lead_type=product | Low |

### Fields to REMOVE from UI (keep in DB):
- pricing_proposal (→ replaced by engagement_status)
- pricing_proposal_details (→ replaced by engagement_status)
- expected_revenue (→ replaced by expected_fee)
- expected_decision_date (→ removed per V17)
- date_committed (→ confirmed removal)
- date_declined (→ confirmed removal)

### Fields to MODIFY:
- rating: merge 3 lost types → "did_not_win"
- relationship: new→new_client, cross_sell→existing_client_new_business, etc.
- risk_weight: high/medium/low → 0-25%/25-50%/50-75%/75-100%
- asset_class: split by service type via parent_value scoping
- source: change from required→suggested at Radar
- summary: max 200→250 chars
- service_type: rename "discretionary"→"investment_management"
- rfp_status: convert to auto-populated boolean from engagement_status

### Key Business Logic:
1. **Engagement Status cascading defaults** — When Rating advances, Engagement Status auto-sets to minimum
2. **RFP as auto-boolean** — Y if engagement_status in (rfp_expected, rfp_in_progress)
3. **Prospect→Client transition** — When lead won, org relationship_type changes prospect→client
4. **Service-type-specific revenue sections** — IM gets fee fields, Product gets commitment, Service gets flat fee

---

## Activities CSV Structure

| CSV Column | Echo 2.0 Field | Notes |
|-----------|---------------|-------|
| cr932_crmactivityid (GUID) | Links to ActivityEntities.activity | Primary join key |
| cr932_title | title | Direct |
| cr932_type (1-4) | activity_type | Needs ID mapping |
| cr932_author | author_id | Match on display name |
| cr932_effectivedate | effective_date | Date parse |
| cr932_descriptionplaintext | details | Direct (can be very large) |
| cr932_orgnames (pipe-separated) | activity_organization_links | Match orgs by name |
| cr932_peoplefullname (pipe-separated) | activity_people_links | Match people by name |
| cr932_isdeleted | is_archived | Boolean |

---

## Field Mapping: Organizations (5,383 rows)

| CRM Field | Echo 2.0 Field | Transform |
|-----------|---------------|-----------|
| organizationid | power_apps_id (EAV) | UUID passthrough for FK matching |
| organizationname | company_name | Direct |
| shortname | short_name | Direct |
| entitytype | organization_type | ID→text mapping (complete) |
| aummncurrency_base | aum_mn | Numeric |
| aumasofdate | aum_as_of_date | Date |
| aumsource | aum_source | Direct |
| website | website | Direct |
| address | street_address | Direct |
| country | country | Normalize text→reference_data value |
| city | city | Direct |
| state | state_province | Direct |
| zipcode | postal_code | Direct |
| rfphold | rfp_hold | Boolean |
| targetallocationsource | target_allocation_source | Direct |
| teamdistributionlist | team_distribution_email | Direct |
| hedgefundtargetallocationoftotalaum | hf_target_allocation_pct | Numeric |
| privatecredittargetallocationoftotalaum | pc_target_allocation_pct | Numeric |
| privateequitytargetallocationoftotalaum | pe_target_allocation_pct | Numeric |
| realassetstargetallocationoftotalaum | ra_target_allocation_pct | Numeric |
| realestatetargetallocationoftotalaum | re_target_allocation_pct | Numeric |
| relationshiptype | relationship_type | ID→text mapping (complete) |
| clientquestionnairetoggle | client_discloses_info | Boolean |
| overallclientaum | overall_aum_mn | Numeric |
| clientquestionaireauthor | questionnaire_filled_by | User name→UUID |
| aksiallc_clientquestionnairecompletedon | questionnaire_date | Date |
| ostrakoid / ostrakoidnum | ostrako_id | Direct |
| coverage, coverage2-5 | → person_coverage_owners (on linked people) | Match user names |
| coverageoffice | coverage_office (new EAV or core field) | ID→text mapping (complete) |
| orgid | backstop_company_id | Legacy integer ID |
| Skip: cleanorgname, cleanshortname, calculatedfieldcoverage, exchangerate, additionalcoverage | Computed fields | — |

## Field Mapping: People (12,912 rows)

| CRM Field | Echo 2.0 Field | Transform |
|-----------|---------------|-----------|
| peopleid | power_apps_id (EAV) | UUID for FK matching |
| orgid | person_organization_links.organization_id | Match org by legacy ID |
| title | job_title | Direct |
| email | email | Direct |
| firstname | first_name | Direct |
| lastname | last_name | Direct |
| phone | phone | Direct |
| mobilephone | (store in EAV or append) | Text |
| donotcontact | do_not_contact | Boolean (0→false) |
| legalcompliancenotices | legal_compliance_notices | Boolean |
| *_publications (11 cols) | distribution_list_members | Value=2 → L2 member. Value=4 → L1 member. Value=5 → L1 (downgraded from L2). Values 1,3 → skip. |
| personid | (legacy integer ID) | Store as EAV |
| Skip: fullname, fullnameorg, shortnameorg, org*, reviewed* | Computed/denormalized | — |

## Field Mapping: Leads (2,456 rows)

| CRM Field | Echo 2.0 Field | Transform |
|-----------|---------------|-----------|
| leadsid | power_apps_id (EAV) | UUID for FK matching |
| organizationlinked | organization_id | Match org by legacy UUID |
| aksiallc_leadname | title | Direct |
| leadstatus | rating | ID→text mapping (complete) |
| engagementstatus | engagement_status | ID→text mapping (complete) |
| servicetype | service_type | ID→text mapping (complete — 7 values including advisory_bps) |
| assetclasstxt | asset_classes | Parse comma text→array |
| relationship | relationship | ID→text mapping (complete) |
| rfpstatus | rfp_status | ID→text mapping (complete) |
| typeofpricingproposal | (historical — keep in EAV) | ID→text mapping (complete) |
| riskweight | risk_weight | ID→text mapping (complete) |
| owner | aksia_owner_id + lead_owners | Match user by display name |
| createddate | start_date / created_at | Date |
| leadenddate | end_date | Date |
| expectedlongtermflar_base | expected_longterm_flar | Numeric (USD) |
| expectedyear1flar_base | expected_yr1_flar | Numeric (USD) |
| expectedrevenueinclperffees_base | expected_revenue → expected_fee | Numeric (USD) |
| expectedrevenuenotes | expected_revenue_notes | Direct |
| expecteddecisiondate | expected_decision_date (historical) | Date |
| expectedrfpdate | rfp_expected_date | Date |
| pricingproposaldetails | (historical — keep in EAV) | Direct |
| summary | summary | Direct |
| leadsource | source | Direct |
| nextsteps | next_steps (renamed "follow_up") | Direct |
| nextstepsdate | next_steps_date (renamed "follow_up_date") | Date |
| legacyonboarding | legacy_onboarding | Boolean |
| legacyonboardingholdings | legacy_onboarding_holdings | Direct |
| declinerationale | decline_rationale | Direct |
| whydeclined | decline_reason | ID→text mapping (complete) |
| waystoneapproved | waystone_approved | ID→text mapping (complete) |
| internalclientstatusinitialreview | commitment_status | ID→text mapping (complete) |
| prospectcontacteddate | prospect_contacted_date | Date |
| prospectrespondeddate | prospect_responded_date | Date |
| initialmeetingdate | initial_meeting_date | Date |
| initialmeetingcompleted | initial_meeting_complete_date | Boolean→Date |
| indicativesizehigh | indicative_size_high | Numeric |
| indicativesizelow | indicative_size_low | Numeric |
| aksiallc_currency | revenue_currency | ID→text (PENDING) |
| aksiallc_managementfee | expected_management_fee | Numeric |
| aksiallc_incentivefee | expected_incentive_fee | Numeric |
| aksiallc_preferredreturn | expected_preferred_return | Numeric |
| aksiallc_coverageoffice | coverage_office | ID→text mapping (complete) |
| aksiallc_gpcommitment | gp_commitment | Text |
| aksiallc_deploymentperiod | deployment_period | Text |
| aksiallc_expectedcontractstartdate | expected_contract_start_date | Date |
| currentstatus | Active→is_archived=false, else true | Status |
| isdeleted | is_archived | Boolean |
| Lead type inference | lead_type | servicetype=5(product)→"product", else→"service" |
| Skip: org*, shortname, exchangerate, backstop*, importsequencenumber | Denormalized/legacy | — |

## Field Mapping: Contracts (404 rows)

| CRM Field | Echo 2.0 Field | Transform |
|-----------|---------------|-----------|
| contractsid | power_apps_id (EAV) | UUID |
| organizationlinked | organization_id | Match org by legacy UUID |
| startdate | start_date | Date |
| enddate | (EAV field) | Date |
| contractservicetype | service_type | Same as lead servicetype mapping |
| contractsummary | summary | Direct |
| assetclasstxt | asset_classes | Parse text→array |
| inflationprovision | inflation_provision | Direct |
| currentstatus | Active→is_archived=false, Inactive→true | Status |
| actualrevenue | actual_revenue | Numeric |
| leadlinked | originating_lead_id | Match lead by legacy UUID |
| clientcoverage | client_coverage | Direct |
| escalatorclause | escalator_clause | Direct |
| contractnotes | (append to summary or EAV) | Text |
| Skip: aksiallc_* (12 fields), backstop*, importsequencenumber | Legacy financial fields | Store as EAV if needed |

---

## Files Affected by Lead Schema Changes (Reference for Future Steps)

When modifying lead-related values (types, stages, field names, reference_data categories), check ALL of these files:

### Python (routers + services)
| File | What to check |
|------|--------------|
| `routers/leads.py` | Stage constants, lead_type defaults, validation rules, form parsing, form context |
| `routers/dashboards.py` | Stage/type filters, LEAD_INACTIVE_STAGES, LEAD_LOST_STAGES, stage colors, coverage widget, drilldown queries |
| `routers/activities.py` | INACTIVE_LEAD_STAGES, lead_type display labels |
| `routers/contracts.py` | Won stage detection, lead_type defaults, pre-fill from lead fields |
| `routers/organizations.py` | _INACTIVE_LEAD_STAGES, fundraise/product lead queries |
| `routers/tasks.py` | Lead type queries for suggested assignees |
| `routers/distribution_lists.py` | Lead type filter for fund-based DL queries |
| `services/form_service.py` | _SERVICE_STAGE_ORDER, _PRODUCT_STAGE_ORDER, _get_stage_order() |
| `services/grid_service.py` | _INACTIVE_STAGES, _DEFAULT_COLUMNS, _BASE_SELECT, _VALID_SORT, lead_type filter logic |
| `scripts/seed_field_definitions.py` | LEAD_FIELDS array |
| `scripts/seed_data.py` | Dummy data generation (lead_type, stages, reference values) |

### Templates
| File | What to check |
|------|--------------|
| `templates/leads/form.html` | Hardcoded field sections, JS stage/type visibility, dropdown context vars |
| `templates/leads/detail.html` | Stage badges, field labels, lead_type display, back-link URLs |
| `templates/leads/list.html` | Lead type filter tabs, page titles |
| `templates/components/_grid.html` | Lead type badge colors |
| `templates/organizations/_org_leads_panel.html` | Lead type badges |
| `templates/organizations/_tab_fundraise_leads.html` | Product lead tab |
| `templates/organizations/detail.html` | Tab labels |
| `templates/dashboards/_widget_my_coverage.html` | Lead count variable names, link URLs |
| `templates/dashboards/advisory_pipeline.html` | Stage references (if any) |
| `templates/dashboards/capital_raise.html` | Stage references, drilldown container IDs |

### Database
| File | What to check |
|------|--------------|
| `db/migrate_schema.sql` | Column definitions, reference_data inserts, data migration UPDATEs |
| `db/schema.sql` | Canonical schema (not always kept in sync — migrate_schema.sql is source of truth) |

---

## Implementation Steps

Each step is self-contained (can clear session between). After each step: update SESSION_LOG.md + this file, commit.

### Step 0: Create Users ✅ COMPLETE (March 30, 2026)
Created real user records from employee list + CRM data. Script: `scripts/create_users.py`.

**Changes made:**
- **create_users.py (NEW):** Loads 434 employees from CSV, extracts 176 unique CRM names from EchoData.xlsx (org coverage, lead owners) + activities CSV (authors). 3-tier matching: exact (134), nickname expansion (0 — all were exact or former), prefix (1: "Alejandro Guerra" → "Alejandro Guerra A"). 41 unmatched names created as inactive former employees. `build_name_to_uuid_map()` returns 537 entries for downstream import.
- **seed_data.py:** Added `person_coverage_owners` and `user_roles` to `tables_to_clean` in `cleanup_seed_data()`.
- **Admin panel:** Added create user (`POST /admin/users/create`), edit user (`POST /admin/users/{user_id}/edit`), "View As" impersonation (`POST /admin/users/{user_id}/view-as`, `POST /admin/view-as/exit`). Updated `admin/users.html` with search/filter, create/edit modals, view-as buttons.
- **dependencies.py:** `get_current_user()` now checks session for `view_as_user_id` to support admin impersonation. Yellow "Viewing as" banner in `base.html`.

**Results:** 434 active users (5 admins: Miles, Aggeliki, Antouella, Clifton, Thalia) + 41 inactive former employees = 475 total. Dev user retained (FK constraints from audit_log/saved_views/duplicates).

**Employee list received:** March 30, 2026.

### Step 1: Lead Schema + V17 Fields ✅ COMPLETE (March 30, 2026)
Add all V17 fields to schema, reference_data, field_definitions. Rename lead_type values (advisory→service, fundraise/product→product). Update rating stages. Add engagement_status cascading logic. Restructure asset classes. Remove deprecated fields from UI. Update form + detail templates.

**Changes made:**
- **migrate_schema.sql (Phase 8):** 29 new columns on leads table. 10 new reference_data categories (engagement_status, commitment_status, waystone_approved, decline_reason_code, coverage_office, gp_commitment, deployment_period, expected_fund_close, revenue_currency, service_subtype placeholder). Updated lead_type (advisory→service, removed fundraise), lead_stage (merged 3 lost→did_not_win, parent_value advisory→service/fundraise→product), lead_relationship_type (renamed 3, added platform_relationship_approval), service_type (discretionary→investment_management, added advisory_bps), risk_weight (high/medium/low→percentage ranges). Data migration UPDATEs for existing leads.
- **seed_field_definitions.py:** LEAD_FIELDS rewritten — 58 fields organized into 13 sections (Basic Information, Overview, Timeline, Focus, Service Details, IM Details, Product Details, RFP, Follow-Up, Verbal Mandate, Fund & Allocation, Closure). Removed pricing_proposal, pricing_proposal_details, expected_revenue, expected_decision_date, rfp_status, rfp_expected_date from UI. Added engagement_status, coverage_office, service_subtype, includes_product_allocation, includes_max_access, 4 timeline dates, indicative_size_low/high, expected_fee, 4 IM fee fields, expected_size, gp_commitment, deployment_period, commitment_status, waystone_approved, expected_fund_close, rfp_due_date, rfp_submitted_date, decline_reason_code, decline_rationale.
- **leads.py:** STAGE_ORDER updated (did_not_win replaces 3 lost stages). PRODUCT_STAGE_ORDER (renamed from FUNDRAISE_). _ENGAGEMENT_DATE_FIELDS for auto-date population. _build_lead_data_from_form rewritten for all V17 fields. _validate_lead_fields updated (removed pricing_proposal/expected_revenue requirements, source now suggested not required). Engagement status auto-sets timeline dates on create/update. All "advisory"→"service", "fundraise"→"product" references.
- **form_service.py:** _SERVICE_STAGE_ORDER, _PRODUCT_STAGE_ORDER (renamed). Default lead_type "service".
- **grid_service.py:** Updated _INACTIVE_STAGES, _DEFAULT_COLUMNS (engagement_status replaces expected_revenue), _BASE_SELECT (added V17 columns).
- **Templates:** form.html, detail.html, list.html — all updated for service/product, did_not_win, removed pricing_proposal/expected_revenue/expected_decision_date sections. _grid.html, _org_leads_panel.html, _tab_fundraise_leads.html, _widget_my_coverage.html — updated.
- **Other routers:** dashboards.py, activities.py, contracts.py, organizations.py, tasks.py, distribution_lists.py — all updated for V17 stage/type values.

### Step 2: Fundraise → Product Merger + Dashboard Updates ✅ COMPLETE (March 30, 2026)
Renamed all remaining fundraise→product references across 15 files (variables, templates, labels, seed data, DL fund queries). Template renamed _tab_fundraise_leads.html → _tab_product_leads.html. schema.sql baseline updated.

### Step 3: Multi-Coverage + Prospect→Client Workflow ✅ COMPLETE (March 30, 2026)
- **3A:** person_coverage_owners junction table (Phase 9 migration). Dual-write to legacy column. Typeahead autocomplete UI on people form. All queries (dashboard, grid, org rollup, activities, tasks) updated to junction table.
- **3B:** Prospect→client auto-transition when lead rating=won. 5 client_team_coverage EAV fields on orgs (visible+suggested when client).

### Step 4: Import Script — Core Entities ✅ COMPLETE (March 30, 2026)
Built `scripts/import_echo_data.py` — 8-phase import with `--dry-run` (default) and `--apply` flags.

**Changes made:**
- **import_echo_data.py (NEW):** Header-name-based Excel reading, 12 ID→text mapping dicts, 70+ entry country normalization map, safe value helpers. 8 phases: setup → reference_data → field_defs → cleanup → orgs → people → leads → contracts → EAV.
- **Phase 1:** Upserted 14 new organization_type values + 55 new country codes into reference_data.
- **Phase 2:** Created power_apps_id EAV field_definitions for 4 entity types.
- **Phase 3:** Hard-deleted all existing entity data (cleanup for fresh import).
- **Phase 4:** 5,383 organizations imported. All org types mapped. 1 unmapped country ("77479" — zip code). Target allocation pcts clamped to max 100 (1 bad data point at 30M).
- **Phase 5:** 12,912 people imported. 11,986 person_organization_links created (25 org not found, 901 no orgid).
- **Phase 6:** 2,451 leads imported (5 skipped — no matching org). 2,441 lead_owners created. 46 leads without owner. Lead type inferred from service_type (5=product, else=service).
- **Phase 7:** 404 contracts imported. 353 placeholder leads created for contracts without `leadlinked` (NOT NULL constraint on originating_lead_id). 51 contracts matched to real leads.
- **Phase 8:** 20,746 EAV power_apps_id values stored (orgs + people + leads).

**Results:** 5,383 orgs, 12,912 people, 2,804 leads (2,451 real + 353 placeholders), 404 contracts, 11,986 org links, 2,441 lead owners, 20,746 EAV values.

**Currency mapping resolved:** IDs [1, 2, 7] → [USD, EUR, CAD].

### Step 5: Import Script — Activities ✅ COMPLETE (March 31, 2026)
Import 27.4K activities from CSV + create org/person links from ActivityEntities.xlsx.

**Changes made:**
- **import_echo_data.py:** Extended with Phases 9-10 (~370 lines added).
- **Phase 9:** Streaming CSV import of 27K+ activities. `ACTIVITY_TYPE_MAP` (1-4→call/meeting/note/email). `ensure_legacy_author()` creates system user for PA legacy placeholder. Author matching via `build_name_to_uuid_map()`. Details capped at 100K chars (tsvector index limit). `safe_date()` updated for fractional seconds. Batch size = 10 (large text fields).
- **Phase 10:** Activity links from ActivityEntities Excel sheet (76,964 rows). `build_pa_entity_maps()` rebuilds PA→Echo UUID maps from EAV table (for standalone runs). `import_activity_links()` resolves entity type (1=org, 2=person), deduplicates, creates `activity_organization_links` and `activity_people_links`. Batch size = 50.
- `activity_lead_links` added to `CLEANUP_TABLES` for re-runnable imports.

### Step 6: Import Script — Distribution Lists + Coverage ✅ COMPLETE (March 31, 2026)
DL membership from People publication columns + coverage from org coverage fields.

**Changes made:**
- **import_echo_data.py:** Phase 11 (create 18 publication DLs + 10,717 memberships) + Phase 12 (17,152 person_coverage_owners from 3,561 orgs). Added `--start-phase`/`--end-phase` flags. `_batch_insert()` retry logic for timeout/502 errors.
- **dashboards.py:** `_get_covered_person_ids()` paginates past 1000-row limit. `_batched_in_query()` chunks .in_() to 200 per batch. All 3 coverage widgets fixed.
- **grid_service.py:** `_execute_batched_query()` for large ID filters — batched execution with in-Python sort/pagination.
- **organizations.py, people.py:** Paginated pco queries + batched .in_() for My Organizations/My People views.

**Results:** 18 DLs (9 categories × L1+L2), 10,717 memberships (4,412 L1 + 6,305 L2), 17,152 coverage owners (9,425 primary + 7,727 secondary, 106 unique users).

### Step 7: Post-Import Validation ✅ COMPLETE (March 31, 2026)

**Row Counts — ALL MATCH:**
| Table | Count |
|---|---|
| organizations | 5,384 (+1 dev org) |
| people | 12,912 |
| person_organization_links | 11,986 |
| leads | 2,804 (2,451 real + 353 placeholders) |
| lead_owners | 2,441 |
| contracts | 404 |
| activities | 27,371 |
| activity_organization_links | 31,173 |
| activity_people_links | 45,069 |
| distribution_lists | 18 |
| distribution_list_members | 10,717 |
| person_coverage_owners | 17,152 |
| entity_custom_values | 20,746 |

**FK Integrity — ALL PASS (0 orphans):**
All 12 FK checks pass with zero orphaned references (lead_owners, person_org_links, DL members, coverage owners, activity org/people links, contracts).

**Page Rendering — ALL PASS:**
Dashboard, Organizations, People, Leads, Activities, Contracts, Distribution Lists, Advisory Pipeline, Capital Raise — all return 200.

**Data Quality — GOOD:**
- Lead types: 962 service, 654 product
- Ratings: 816 exploratory, 305 radar, 125 focus, 17 verbal_mandate, 353 won
- Activities: 12,991 calls, 7,151 meetings, 7,226 notes, 3 emails
- DL membership largest: PANALTS L1 (2,113), PC L2 (1,542), PE L2 (1,337)
- Coverage: top user Harry Seplowitz (1,788 people), 106 unique coverage users

---

## Next Session Prompt

Copy-paste this into a new Claude session to continue:

```
We are continuing work on Echo 2.0 data import. Read these files to get full context:

1. `@CLAUDE.md` — project overview and coding standards
2. `@DATA_IMPORT_PLAN.md` — the comprehensive plan with all decisions, field mappings, implementation steps
3. `@feedback.md` — testing feedback history

**Where we left off:** Steps 0-5 are COMPLETE. All core entities + activities imported:
- 475 users (434 active + 41 inactive former employees)
- 5,383 organizations with country normalization (55 new country codes, 14 new org types)
- 12,912 people with 11,986 person_organization_links
- 2,451 real leads + 353 placeholder leads (for contracts without linked leads)
- 404 contracts, 2,441 lead_owners, 20,746 EAV power_apps_id values
- 27K+ activities imported from CSV with org/person links from ActivityEntities sheet (76,964 link rows)

**Key scripts:**
- `scripts/create_users.py` — user creation + `build_name_to_uuid_map()` (538 entries)
- `scripts/import_echo_data.py` — full import pipeline (Phases 0-10: core entities + activities)

**What to work on next — Step 6: Import Distribution Lists + Coverage:**
Build DL membership + coverage import into `scripts/import_echo_data.py`:

1. **Distribution List Membership** (from People sheet in EchoData.xlsx):
   - 11 publication columns on People rows (e.g. `hedgefunds_publications`, `privatecredit_publications`, etc.)
   - Import logic per column: Value=2 → L2 member. Value=4 → L1 member. Value=5 → L1 member (was L2, downgraded). Values 0, 1, 3 → skip.
   - Need to match publication columns → existing distribution_lists by name/category
   - Create `distribution_list_members` rows linking person_id to list_id

2. **Coverage Import** (from Organizations sheet in EchoData.xlsx):
   - `coverage`, `coverage2`, `coverage3`, `coverage4`, `coverage5` columns contain user display names
   - Match via `build_name_to_uuid_map()` → user UUIDs
   - For each org, find all linked people (via `person_organization_links`)
   - Create `person_coverage_owners` rows: coverage → is_primary=true, coverage2-5 → is_primary=false

**After Step 6:**
- Step 7: Post-import validation (count verification, FK integrity, dashboard rendering, Excel export comparison)
```

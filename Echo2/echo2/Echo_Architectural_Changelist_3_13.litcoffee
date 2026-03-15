# Echo 2.0 — Architectural Changelist from Patrick/Miles Alignment Call
# Date: March 2026
# Status: APPROVED — Implement all changes below

## CONTEXT
Patrick (senior partner) and Miles reviewed the current prototype and agreed on
significant architectural changes. The core theme: move from hard-coded fields
and views to a flexible, admin-configurable system using a hybrid EAV schema.
This requires a substantial rebuild of the current schema and codebase.

The current codebase has 20 tables and 45 files built on a standard PostgreSQL
schema with hardcoded fields. We are converting to a hybrid EAV architecture.

## CHANGE 1: HYBRID EAV SCHEMA CONVERSION [CRITICAL — DO FIRST]

### What to build:
1. Create a `field_definitions` table:
   - id (UUID, PK)
   - entity_type (VARCHAR — 'organization', 'person', 'lead', 'contract', 'activity', 'document')
   - field_name (VARCHAR, unique per entity_type)
   - display_name (VARCHAR)
   - field_type (VARCHAR — 'text', 'number', 'date', 'boolean', 'dropdown', 'multi_select', 'lookup', 'address', 'phone', 'currency', 'calculated', 'url', 'email', 'textarea')
   - storage_type (VARCHAR — 'core_column' or 'eav')
   - is_required (BOOLEAN, default false)
   - is_system (BOOLEAN, default true for built-in fields, false for admin-created)
   - display_order (INTEGER)
   - section_name (VARCHAR — for grouping fields into sections on forms)
   - validation_rules (JSONB — min/max, regex, allowed values, etc.)
   - dropdown_options (JSONB — for dropdown/multi_select types, array of {value, label})
   - calculation_expression (TEXT — for calculated field type, formula referencing other field_names)
   - default_value (TEXT)
   - is_active (BOOLEAN, default true)
   - created_at, updated_at, created_by

2. Create an `entity_custom_values` table (EAV storage):
   - id (UUID, PK)
   - entity_type (VARCHAR)
   - entity_id (UUID)
   - field_definition_id (UUID, FK → field_definitions)
   - value_text (TEXT)
   - value_number (NUMERIC)
   - value_date (TIMESTAMPTZ)
   - value_boolean (BOOLEAN)
   - value_json (JSONB — for multi-select, address objects, etc.)
   - created_at, updated_at
   - UNIQUE constraint on (entity_type, entity_id, field_definition_id)

3. Keep these as CORE COLUMNS on entity base tables (high-frequency query fields):
   - organizations: id, name, org_type, country, city, state, relationship_type, is_deleted, created_at, updated_at, created_by
   - people: id, first_name, last_name, email, phone, title, primary_org_id, is_deleted, created_at, updated_at, created_by
   - leads: id, org_id, lead_type, stage, service_type, is_deleted, created_at, updated_at, created_by
   - contracts: id, lead_id, org_id, status, is_deleted, created_at, updated_at, created_by
   - activities: id, activity_type, activity_date, subject, notes, created_by, is_deleted, created_at, updated_at

4. All other fields that were previously hardcoded columns should be migrated to
   field_definitions with storage_type='eav' and their values stored in
   entity_custom_values. This includes fields like: AUM, website, linkedin,
   address fields, coverage team, service-specific fields on leads, etc.

5. Update ALL form rendering:
   - When rendering a create/edit form for any entity, query field_definitions
     WHERE entity_type = X AND is_active = true ORDER BY display_order
   - For core_column fields, read/write directly to the entity table
   - For eav fields, read/write to entity_custom_values
   - Group fields by section_name

6. Update ALL list/screener views:
   - Column selection should be driven by field_definitions
   - Core columns can be filtered/sorted via SQL WHERE/ORDER BY
   - EAV columns require JOIN to entity_custom_values for filtering

### What NOT to do:
- Do NOT build cross-entity formula references (keep calculated fields same-entity only)
- Do NOT build a dependency DAG engine — simple formula evaluation is fine for now
- Do NOT build real-time column migration between core↔eav — that requires a developer

---

## CHANGE 2: MERGE FUND PROSPECTS INTO LEADS [CRITICAL]

### What to do:
1. DELETE the `fund_prospects` table and any related tables/views/routes.
2. ADD a `lead_type` field to the leads table or field_definitions:
   - Values: 'advisory', 'product', 'fundraise' (admin-configurable dropdown)
3. ENSURE lead stages accommodate all former fund prospect stages.
   - NOTE: Patrick said Echo's current sprint is reconciling all lead stages.
     Check with Patrick for the latest stage list before hardcoding anything.
     Stages should be admin-configurable via field_definitions dropdown.
4. UPDATE all navigation: remove "Fund Prospects" from sidebar.
5. UPDATE dashboard: remove Capital Raise dashboard as separate entity.
   Fund-related leads are now filtered views within the unified Leads module.
6. UPDATE any references in the codebase that import/reference fund_prospects.

---

## CHANGE 3: ADD DOCUMENTS/ATTACHMENTS TABLE

### What to do:
1. CREATE `documents` table:
   - id (UUID, PK)
   - title (VARCHAR)
   - file_url (TEXT — URL or Supabase storage path)
   - file_type (VARCHAR — 'pdf', 'docx', 'xlsx', 'link', etc.)
   - file_size (INTEGER, nullable — bytes)
   - entity_type (VARCHAR — 'organization', 'person', 'lead', 'contract', 'event')
   - entity_id (UUID)
   - uploaded_by (UUID, FK → users)
   - uploaded_at (TIMESTAMPTZ, default now())
   - is_deleted (BOOLEAN, default false)

2. ADD a "Documents" tab/section to detail pages for: Organization, Person, Lead, Contract.
3. Simple UI: list of attached docs with title, type, upload date, uploader. "Add Document" button opens a form with title + file upload or URL input.
4. No versioning, no preview, no workflow for now.

---

## CHANGE 4: MULTI-ROLE DYNAMIC ASSIGNMENT

### What to do:
1. CREATE `roles` table:
   - id (UUID, PK)
   - name (VARCHAR, unique)
   - description (TEXT)
   - permissions (JSONB — structure: { "organizations": {"create": true, "read": true, "update": true, "delete": false}, "leads": {...}, "contracts": {...}, ... })
   - is_system (BOOLEAN — true for built-in roles, cannot be deleted)
   - created_at, updated_at

2. CREATE `user_roles` junction table:
   - user_id (UUID, FK → users)
   - role_id (UUID, FK → roles)
   - assigned_at (TIMESTAMPTZ)
   - assigned_by (UUID, FK → users)
   - PK: (user_id, role_id)

3. SEED initial roles:
   - Admin (full CRUD on all entities + admin panel access)
   - Legal (read all + create/edit Contracts)
   - RFP Team (standard + edit RFP-specific fields)
   - BD (standard + lead ownership semantics)
   - Standard (CRUD on Orgs/People/Activities/Leads, no delete)
   - Read Only (read all, export only)

4. REMOVE the hardcoded `role` column from the `users` table.
5. UPDATE all permission checks: aggregate permissions across all assigned roles (additive).
6. UPDATE the admin panel to include role CRUD + user↔role assignment UI.

---

## CHANGE 5: PERSON↔ORG DATE TRACKING

### What to do:
1. ADD columns to `person_organizations` junction table:
   - start_date (DATE, nullable)
   - end_date (DATE, nullable)
2. When a person's primary org changes:
   - Set end_date = today on the old link
   - Set start_date = today on the new link
   - Mark old link as 'former'
3. UI: hide "Secondary" org field by default. Only show when user explicitly
   adds a secondary affiliation (Patrick: "one out of a thousand" case).

---

## CHANGE 6: MULTIPLE LEAD OWNERS

### What to do:
1. REPLACE `aksia_owner_id` (single FK) on leads with a junction table:
   - `lead_owners` (lead_id UUID FK, user_id UUID FK, PK: (lead_id, user_id))
2. UPDATE Lead create/edit forms: multi-select for Aksia owners.
3. VALIDATION: at least one owner required on every lead.

---

## CHANGE 7: ACTIVITY↔ORG RELATIONSHIP — KEEP AS-IS

No change needed. Current one-to-many junction table is correct.
- Activities link to 1+ organizations (at least one required).
- Activities link to 0+ people.
- When linking an org, auto-populate people dropdown with that org's contacts.
- For individuals without an org (family office), create an org with the person's name.

---

## CHANGE 8: REUSABLE GRID COMPONENT

### What to build:
Create a single, reusable table/grid component used across ALL list views.

Features:
1. Column selector: user can show/hide any field from field_definitions for that entity
2. Column reordering: drag or arrow buttons to rearrange column order
3. Per-column sorting: click column header to sort asc/desc
4. Per-column filtering: click filter icon on any column to set filter criteria
5. Top-level dropdown filters: user can pin specific fields as quick-filter
   dropdowns above the table (e.g., Country, Relationship Type)
6. Saved views: user can save current configuration (columns, filters, sort)
   as a named view. System provides default views.
7. Pagination: server-side, unlimited rows

Deploy on: Organizations, People, Leads, Activities, Distribution Lists,
Contracts, Documents — every list view in the application.

---

## CHANGE 9: LEAD CONTRACT CREATION

### What to change:
- REMOVE auto-creation of Contract when Lead stage = "Won"
- Only users with Legal role can create Contract records
- Contract.lead_id links back to the originating Lead (1:1)
- Exact UI flow TBD — defer detailed implementation until Lead UI is stable
- For now: add a "Create Contract" button on Lead detail page, visible only to Legal role users

---

## CHANGE 10: ADMIN CONTROL PANEL

### What to build:
Create admin-only pages (route guard: user must have Admin role) with:

1. **Field Management** (per entity type):
   - List all field_definitions for the selected entity type
   - Add new field: name, display name, type, storage type, required, validation, section
   - Edit existing fields (except is_system fields cannot be deleted)
   - Reorder fields (drag or up/down arrows)
   - Special field types with built-in formatting:
     - Address: structured fields (street, city, state, zip, country) with masking
     - Phone: country code selector + number with formatting
     - Currency: currency selector + amount with proper formatting
     - Calculated: formula input referencing other field names on same entity

2. **Page Layout Designer** (per entity type):
   - Define which fields appear on the VIEW page (detail/read-only page)
   - Define which fields appear on the ADD/EDIT page (form page)
   - Group fields into named sections
   - Set display order within sections
   - These can be different — view page may show more fields than edit page

3. **Role Management**:
   - List all roles
   - Create/edit roles: name, description, entity-level permissions (CRUD per entity)
   - Assign users to roles (multi-role)
   - System roles (Admin, Legal, etc.) can be edited but not deleted

4. **User Management**:
   - List all users (auto-provisioned via Entra ID SSO)
   - Assign/remove roles
   - Deactivate users (soft delete)

---

## CHANGE 11: LEAD FINDER SAVED VIEW

### What to build:
On the Organizations grid/screener:
1. Add a virtual/calculated column: "Active Leads" — count of leads linked to
   this org where status is active
2. Add filter: "Has Active Lead: Yes / No"
3. When user clicks the Active Leads count for an org:
   - Show a popover or expandable row listing all active leads
   - Each lead row shows: lead type, stage, owner(s), rating
   - Stage and rating should be editable inline
4. When Active Leads = 0, show a "Create Lead" button that opens a pre-filled
   Lead creation form with the org already linked
5. Save this as a default saved view named "Lead Finder"

---

## CHANGE 12: DISTRIBUTION LIST IMPROVEMENTS

1. On Person detail page: add "Distribution Lists" section showing current
   memberships + "Add to List" dropdown/button
2. In DL member search/filter UI: add "Add All" button to bulk-add filtered results
3. Keep existing DL module workflow (it works fine)

---

## CHANGE 13: FOLLOW-UP TASK ASSIGNMENT

- Change follow-up assignee field from "current user only" to a dropdown
  populated with all users assigned to coverage of any linked person or org
- Default selection: activity author
- Allow override to any coverage team member

---

## CHANGE 14: SOFT DELETE POLICY

- Keep soft delete (is_deleted boolean on all tables)
- REMOVE the 90-day restore window concept
- Soft-deleted records are retained indefinitely in the database
- Daily Supabase backups continue as-is
- Admin can restore any soft-deleted record at any time (no time limit)

---

## CHANGE 15: DUPLICATE DETECTION

### What to build:
1. On SAVE of a new Organization:
   - Check name similarity (fuzzy match, >80%) against existing orgs
   - Check domain/website match
   - If matches found: show modal "Similar organizations found: [list with links].
     Is this a duplicate? [Yes → go to existing record] [No → save as new]"
   - If user confirms "not a duplicate," store suppression (pair of IDs)
     so it doesn't flag again

2. On SAVE of a new Person:
   - Check name + email match against existing people
   - Same modal flow as above

3. Admin panel: "Run Deduplication" button for on-demand batch scan

---

## PHASE 2 ITEMS (DO NOT BUILD NOW — just noting for reference)

- Events module (full entity + Event Participation + UI)
- Fee arrangements (complex contract fee tracking)
- Generalized alerts panel (user-configurable triggers)
- Dashboard widget framework (user-created widgets)
- Outlook email integration
- Astroco replacement for research team
- Historical contract backfill
- API exposure for reporting tools

---

## SEQUENCE OF IMPLEMENTATION

Recommended order to minimize rework:

1. field_definitions + entity_custom_values tables (Change 1)
2. roles + user_roles tables (Change 4)
3. documents table (Change 3)
4. lead_owners junction table (Change 6)
5. person_organizations date columns (Change 5)
6. Merge fund_prospects into leads (Change 2)
7. Admin control panel — field management (Change 10.1)
8. Update all entity CRUD to use field_definitions for form rendering
9. Reusable grid component (Change 8)
10. Admin control panel — page layout designer (Change 10.2)
11. Admin control panel — role management (Change 10.3)
12. Lead Finder saved view (Change 11)
13. Distribution list improvements (Change 12)
14. Follow-up task assignment (Change 13)
15. Duplicate detection (Change 15)
16. Lead→Contract manual creation flow (Change 9)
-- =============================================================================
-- Echo 2.0 — Schema Migration (Phases 1–5)
-- Run this in the Supabase SQL Editor to bring the database up to date.
-- Safe to run multiple times (uses IF NOT EXISTS / exception handling).
-- =============================================================================

-- =====================================================================
-- Phase 2: Add missing columns to leads table
-- =====================================================================

ALTER TABLE leads ADD COLUMN IF NOT EXISTS lead_type TEXT NOT NULL DEFAULT 'advisory';
ALTER TABLE leads ADD COLUMN IF NOT EXISTS fund_id UUID REFERENCES funds(id);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS share_class TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS decline_reason TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS target_allocation_mn NUMERIC(15, 2);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS soft_circle_mn NUMERIC(15, 2);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS hard_circle_mn NUMERIC(15, 2);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS probability_pct INT CHECK (probability_pct >= 0 AND probability_pct <= 100);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS stage_entry_date DATE DEFAULT CURRENT_DATE;

CREATE INDEX IF NOT EXISTS idx_leads_type ON leads (lead_type);

-- Phase 2: Add lead_type and fundraise-scoped lead_stage reference_data
INSERT INTO reference_data (category, value, label, display_order)
VALUES
    ('lead_type', 'advisory', 'Advisory', 1),
    ('lead_type', 'product', 'Product', 2),
    ('lead_type', 'fundraise', 'Fundraise', 3)
ON CONFLICT (category, value) DO NOTHING;

-- Phase 1.5: Add date tracking to person_organization_links
ALTER TABLE person_organization_links ADD COLUMN IF NOT EXISTS start_date DATE;
ALTER TABLE person_organization_links ADD COLUMN IF NOT EXISTS end_date DATE;

-- =====================================================================
-- Phase 1: field_definitions + entity_custom_values
-- =====================================================================

CREATE TABLE IF NOT EXISTS field_definitions (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type             TEXT NOT NULL,
    field_name              TEXT NOT NULL,
    display_name            TEXT NOT NULL,
    field_type              TEXT NOT NULL CHECK (field_type IN (
        'text', 'number', 'date', 'boolean', 'dropdown', 'multi_select',
        'lookup', 'address', 'phone', 'currency', 'calculated', 'url',
        'email', 'textarea'
    )),
    storage_type            TEXT NOT NULL DEFAULT 'core_column'
                                CHECK (storage_type IN ('core_column', 'eav')),
    is_required             BOOLEAN NOT NULL DEFAULT FALSE,
    is_system               BOOLEAN NOT NULL DEFAULT TRUE,
    display_order           INT NOT NULL DEFAULT 0,
    section_name            TEXT,
    validation_rules        JSONB DEFAULT '{}',
    dropdown_category       TEXT,
    dropdown_options        JSONB,
    calculation_expression  TEXT,
    default_value           TEXT,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    visibility_rules        JSONB DEFAULT '{}',
    grid_default_visible    BOOLEAN NOT NULL DEFAULT TRUE,
    grid_sortable           BOOLEAN NOT NULL DEFAULT TRUE,
    grid_filterable         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by              UUID REFERENCES users(id),
    UNIQUE(entity_type, field_name)
);

CREATE INDEX IF NOT EXISTS idx_fd_entity ON field_definitions (entity_type);
CREATE INDEX IF NOT EXISTS idx_fd_entity_active ON field_definitions (entity_type) WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS entity_custom_values (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type         TEXT NOT NULL,
    entity_id           UUID NOT NULL,
    field_definition_id UUID NOT NULL REFERENCES field_definitions(id),
    value_text          TEXT,
    value_number        NUMERIC(15, 2),
    value_date          DATE,
    value_boolean       BOOLEAN,
    value_json          JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(entity_type, entity_id, field_definition_id)
);

CREATE INDEX IF NOT EXISTS idx_ecv_entity ON entity_custom_values (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_ecv_field ON entity_custom_values (field_definition_id);

-- =====================================================================
-- Phase 1: roles + user_roles
-- =====================================================================

CREATE TABLE IF NOT EXISTS roles (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    role_name       TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    description     TEXT,
    permissions     JSONB NOT NULL DEFAULT '{}',
    is_system       BOOLEAN NOT NULL DEFAULT FALSE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed system roles (skip if already exist)
INSERT INTO roles (role_name, display_name, description, is_system, permissions) VALUES
    ('admin', 'Admin', 'Full access to all entities and admin panel', TRUE,
     '{"entities": {"organization": ["create","read","update","delete","archive","restore"], "person": ["create","read","update","delete","archive","restore"], "lead": ["create","read","update","delete","archive","restore"], "contract": ["create","read","update","delete","archive","restore"], "activity": ["create","read","update","delete","archive","restore"], "task": ["create","read","update","delete","archive","restore"], "distribution_list": ["create","read","update","delete","archive","restore"], "document": ["create","read","update","delete"]}, "admin_panel": true, "manage_users": true, "manage_roles": true, "manage_fields": true}'),
    ('legal', 'Legal', 'View all entities, create and edit Contracts', TRUE,
     '{"entities": {"organization": ["read"], "person": ["read"], "lead": ["read"], "contract": ["create","read","update"], "activity": ["read"], "task": ["read"], "distribution_list": ["read"], "document": ["read"]}, "create_contract": true}'),
    ('rfp_team', 'RFP Team', 'Standard access plus RFP-specific field editing', TRUE,
     '{"entities": {"organization": ["create","read","update"], "person": ["create","read","update"], "lead": ["create","read","update"], "activity": ["create","read","update"], "task": ["create","read","update"], "distribution_list": ["create","read","update"], "document": ["create","read","update","delete"]}, "rfp_hold": true}'),
    ('bd', 'BD', 'Business Development — standard access plus lead ownership', TRUE,
     '{"entities": {"organization": ["create","read","update"], "person": ["create","read","update"], "lead": ["create","read","update"], "activity": ["create","read","update"], "task": ["create","read","update"], "distribution_list": ["read"], "document": ["create","read","update","delete"]}}'),
    ('standard_user', 'Standard User', 'Create and edit Orgs, People, Activities, Leads', TRUE,
     '{"entities": {"organization": ["create","read","update"], "person": ["create","read","update"], "lead": ["create","read","update"], "activity": ["create","read","update"], "task": ["create","read","update"], "distribution_list": ["create","read","update"], "document": ["create","read","update","delete"]}}'),
    ('read_only', 'Read Only', 'View and export only', TRUE,
     '{"entities": {"organization": ["read"], "person": ["read"], "lead": ["read"], "contract": ["read"], "activity": ["read"], "task": ["read"], "distribution_list": ["read"], "document": ["read"]}, "export": true}')
ON CONFLICT (role_name) DO NOTHING;

CREATE TABLE IF NOT EXISTS user_roles (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id         UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    assigned_by     UUID REFERENCES users(id),
    assigned_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, role_id)
);

CREATE INDEX IF NOT EXISTS idx_ur_user ON user_roles (user_id);
CREATE INDEX IF NOT EXISTS idx_ur_role ON user_roles (role_id);

-- =====================================================================
-- Phase 1: documents table
-- =====================================================================

CREATE TABLE IF NOT EXISTS documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title           TEXT NOT NULL,
    file_url        TEXT NOT NULL,
    file_type       TEXT,
    file_size       BIGINT,
    entity_type     TEXT NOT NULL,
    entity_id       UUID NOT NULL,
    uploaded_by     UUID NOT NULL REFERENCES users(id),
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_doc_entity ON documents (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_doc_uploaded_by ON documents (uploaded_by);

-- =====================================================================
-- Phase 1: lead_owners junction table
-- =====================================================================

CREATE TABLE IF NOT EXISTS lead_owners (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    is_primary      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(lead_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_lo_lead ON lead_owners (lead_id);
CREATE INDEX IF NOT EXISTS idx_lo_user ON lead_owners (user_id);

-- =====================================================================
-- Phase 3: page_layouts table
-- =====================================================================

CREATE TABLE IF NOT EXISTS page_layouts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type     TEXT NOT NULL,
    layout_type     TEXT NOT NULL DEFAULT 'view',
    sections        JSONB NOT NULL DEFAULT '[]',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pl_entity ON page_layouts (entity_type, layout_type);

-- =====================================================================
-- Phase 4: saved_views table
-- =====================================================================

CREATE TABLE IF NOT EXISTS saved_views (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id),
    entity_type     TEXT NOT NULL,
    view_name       TEXT NOT NULL,
    columns         JSONB NOT NULL DEFAULT '[]',
    filters         JSONB NOT NULL DEFAULT '{}',
    sort_by         TEXT,
    sort_dir        TEXT NOT NULL DEFAULT 'asc',
    is_default      BOOLEAN NOT NULL DEFAULT FALSE,
    is_shared       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sv_user_entity ON saved_views (user_id, entity_type);

-- =====================================================================
-- Phase 5: duplicate_suppressions table
-- =====================================================================

CREATE TABLE IF NOT EXISTS duplicate_suppressions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type     TEXT NOT NULL,
    record_id_a     UUID NOT NULL,
    record_id_b     UUID NOT NULL,
    suppressed_by   UUID NOT NULL REFERENCES users(id),
    suppressed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(entity_type, record_id_a, record_id_b)
);

CREATE INDEX IF NOT EXISTS idx_dup_supp_entity ON duplicate_suppressions (entity_type);

-- =====================================================================
-- Triggers for new tables (safe: CREATE OR REPLACE)
-- =====================================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_field_definitions_updated ON field_definitions;
CREATE TRIGGER trg_field_definitions_updated BEFORE UPDATE ON field_definitions FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS trg_entity_custom_values_updated ON entity_custom_values;
CREATE TRIGGER trg_entity_custom_values_updated BEFORE UPDATE ON entity_custom_values FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS trg_roles_updated ON roles;
CREATE TRIGGER trg_roles_updated BEFORE UPDATE ON roles FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS trg_page_layouts_updated ON page_layouts;
CREATE TRIGGER trg_page_layouts_updated BEFORE UPDATE ON page_layouts FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS trg_saved_views_updated ON saved_views;
CREATE TRIGGER trg_saved_views_updated BEFORE UPDATE ON saved_views FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =====================================================================
-- Phase 5: Rename is_archived → is_deleted
-- (uses DO block to handle "column does not exist" gracefully)
-- =====================================================================

DO $$
BEGIN
    -- Only rename if is_archived exists (skip if already renamed)
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'organizations' AND column_name = 'is_archived') THEN
        ALTER TABLE organizations RENAME COLUMN is_archived TO is_deleted;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'people' AND column_name = 'is_archived') THEN
        ALTER TABLE people RENAME COLUMN is_archived TO is_deleted;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'activities' AND column_name = 'is_archived') THEN
        ALTER TABLE activities RENAME COLUMN is_archived TO is_deleted;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'is_archived') THEN
        ALTER TABLE leads RENAME COLUMN is_archived TO is_deleted;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'contracts' AND column_name = 'is_archived') THEN
        ALTER TABLE contracts RENAME COLUMN is_archived TO is_deleted;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'tasks' AND column_name = 'is_archived') THEN
        ALTER TABLE tasks RENAME COLUMN is_archived TO is_deleted;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'person_organization_links' AND column_name = 'is_archived') THEN
        ALTER TABLE person_organization_links RENAME COLUMN is_archived TO is_deleted;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'activity_organization_links' AND column_name = 'is_archived') THEN
        ALTER TABLE activity_organization_links RENAME COLUMN is_archived TO is_deleted;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'activity_people_links' AND column_name = 'is_archived') THEN
        ALTER TABLE activity_people_links RENAME COLUMN is_archived TO is_deleted;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'fee_arrangements' AND column_name = 'is_archived') THEN
        ALTER TABLE fee_arrangements RENAME COLUMN is_archived TO is_deleted;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'record_tags' AND column_name = 'is_archived') THEN
        ALTER TABLE record_tags RENAME COLUMN is_archived TO is_deleted;
    END IF;
END $$;

-- =====================================================================
-- Update duplicate detection functions to use is_deleted
-- =====================================================================

CREATE OR REPLACE FUNCTION check_org_name_similarity(search_name TEXT, similarity_threshold FLOAT DEFAULT 0.4)
RETURNS TABLE(id UUID, company_name TEXT, website TEXT, organization_type TEXT, relationship_type TEXT)
AS $$
BEGIN
    RETURN QUERY
    SELECT o.id, o.company_name, o.website, o.organization_type, o.relationship_type
    FROM organizations o
    WHERE o.is_deleted = FALSE
      AND similarity(o.company_name, search_name) > similarity_threshold
    ORDER BY similarity(o.company_name, search_name) DESC
    LIMIT 10;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION check_person_name_similarity(
    search_first TEXT,
    search_last TEXT,
    similarity_threshold FLOAT DEFAULT 0.4
)
RETURNS TABLE(id UUID, first_name TEXT, last_name TEXT, email TEXT, job_title TEXT, org_name TEXT)
AS $$
BEGIN
    RETURN QUERY
    SELECT p.id, p.first_name, p.last_name, p.email, p.job_title,
           (SELECT o.company_name
            FROM person_organization_links pol
            JOIN organizations o ON o.id = pol.organization_id
            WHERE pol.person_id = p.id AND pol.link_type = 'primary'
            LIMIT 1) AS org_name
    FROM people p
    WHERE p.is_deleted = FALSE
      AND similarity(p.first_name || ' ' || p.last_name, search_first || ' ' || search_last) > similarity_threshold
    ORDER BY similarity(p.first_name || ' ' || p.last_name, search_first || ' ' || search_last) DESC
    LIMIT 10;
END;
$$ LANGUAGE plpgsql;

-- =====================================================================
-- A6: Add text_list field type
-- =====================================================================

ALTER TABLE field_definitions DROP CONSTRAINT IF EXISTS field_definitions_field_type_check;
ALTER TABLE field_definitions ADD CONSTRAINT field_definitions_field_type_check
    CHECK (field_type IN (
        'text', 'number', 'date', 'boolean', 'dropdown', 'multi_select',
        'lookup', 'address', 'phone', 'currency', 'calculated', 'url',
        'email', 'textarea', 'text_list'
    ));

-- =====================================================================
-- A4: Add suggestion_rules column for "suggested" field concept
-- =====================================================================

ALTER TABLE field_definitions ADD COLUMN IF NOT EXISTS suggestion_rules JSONB DEFAULT '{}';

-- =====================================================================
-- D1: Dynamic distribution lists
-- =====================================================================

ALTER TABLE distribution_lists ADD COLUMN IF NOT EXISTS list_mode TEXT NOT NULL DEFAULT 'static';
ALTER TABLE distribution_lists ADD COLUMN IF NOT EXISTS filter_criteria JSONB NOT NULL DEFAULT '{}';
ALTER TABLE distribution_list_members ADD COLUMN IF NOT EXISTS is_manual BOOLEAN NOT NULL DEFAULT FALSE;
-- Note: list_mode check constraint: CHECK (list_mode IN ('static', 'dynamic'))
-- Apply via: ALTER TABLE distribution_lists ADD CONSTRAINT IF NOT EXISTS dl_list_mode_check CHECK (list_mode IN ('static', 'dynamic'));

-- =====================================================================
-- Phase 6: Linked/calculated fields
-- =====================================================================
ALTER TABLE field_definitions ADD COLUMN IF NOT EXISTS linked_config JSONB;
-- linked_config stores: {"source_entity": "organization", "source_field": "city",
--   "link_via": "person_organization_links" or "direct" (for leads.organization_id)}
-- storage_type 'linked' indicates this is a calculated/linked field.
-- No CHECK constraint change needed — storage_type is already a free TEXT column.

-- =====================================================================
-- Phase 6: View Configurations (admin-configurable view settings)
-- =====================================================================

CREATE TABLE IF NOT EXISTS view_configurations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    view_key        TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    description     TEXT,
    category        TEXT NOT NULL DEFAULT 'general',
    config          JSONB NOT NULL DEFAULT '{}',
    updated_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_vc_key ON view_configurations (view_key);

-- =====================================================================
-- Activity <-> Lead Links
-- =====================================================================

CREATE TABLE IF NOT EXISTS activity_lead_links (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    activity_id UUID NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    lead_id     UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(activity_id, lead_id)
);

CREATE INDEX IF NOT EXISTS idx_all_activity ON activity_lead_links (activity_id);
CREATE INDEX IF NOT EXISTS idx_all_lead ON activity_lead_links (lead_id);

-- =====================================================================
-- Phase 7: Lead title, lead_stage ref data, org asset_class
-- =====================================================================

-- Add title column to leads
ALTER TABLE leads ADD COLUMN IF NOT EXISTS title TEXT;

-- Ensure lead_stage reference data exists (may not have been seeded)
INSERT INTO reference_data (category, value, label, parent_value, display_order) VALUES
    ('lead_stage', 'exploratory', 'Open [Exploratory]', 'advisory', 1),
    ('lead_stage', 'radar', 'Open [Radar]', 'advisory', 2),
    ('lead_stage', 'focus', 'Open [Focus]', 'advisory', 3),
    ('lead_stage', 'verbal_mandate', 'Open [Verbal Mandate - In Contract]', 'advisory', 4),
    ('lead_stage', 'won', 'Inactive [Won Mandate – Aksia Client]', 'advisory', 5),
    ('lead_stage', 'lost_dropped_out', 'Inactive [Lost – Aksia Dropped Out]', 'advisory', 6),
    ('lead_stage', 'lost_selected_other', 'Inactive [Lost – Selected Someone Else]', 'advisory', 7),
    ('lead_stage', 'lost_nobody_hired', 'Inactive [Lost – Nobody Hired]', 'advisory', 8),
    ('lead_stage', 'target_identified', 'Target Identified', 'fundraise', 1),
    ('lead_stage', 'intro_scheduled', 'Intro Scheduled', 'fundraise', 2),
    ('lead_stage', 'initial_meeting_complete', 'Initial Meeting Complete', 'fundraise', 3),
    ('lead_stage', 'ddq_materials_sent', 'DDQ / Materials Sent', 'fundraise', 4),
    ('lead_stage', 'due_diligence', 'Due Diligence', 'fundraise', 5),
    ('lead_stage', 'ic_review', 'IC Review', 'fundraise', 6),
    ('lead_stage', 'soft_circle', 'Soft Circle', 'fundraise', 7),
    ('lead_stage', 'legal_docs', 'Legal / Docs', 'fundraise', 8),
    ('lead_stage', 'closed', 'Closed', 'fundraise', 9),
    ('lead_stage', 'declined', 'Declined', 'fundraise', 10)
ON CONFLICT (category, value) DO NOTHING;

-- Add asset_class and product_funds to organizations (for client orgs)
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS asset_class TEXT[];
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS product_funds TEXT[];

-- Reference data for org asset class
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('org_asset_class', 'hf', 'HF', 1),
    ('org_asset_class', 'pc', 'PC', 2),
    ('org_asset_class', 'pe', 'PE', 3),
    ('org_asset_class', 'ra', 'RA', 4),
    ('org_asset_class', 'product', 'Product', 5)
ON CONFLICT (category, value) DO NOTHING;

-- Reference data for product funds (shown when asset_class includes 'product')
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('org_product_fund', 'apc', 'APC', 1),
    ('org_product_fund', 'capix', 'CAPIX', 2),
    ('org_product_fund', 'capvx', 'CAPVX', 3),
    ('org_product_fund', 'hedgx', 'HEDGX', 4)
ON CONFLICT (category, value) DO NOTHING;

-- =====================================================================
-- Done! Verify with:
--   SELECT column_name FROM information_schema.columns WHERE table_name = 'people' AND column_name = 'is_deleted';
--   SELECT count(*) FROM field_definitions;
--   SELECT column_name FROM information_schema.columns WHERE table_name = 'field_definitions' AND column_name = 'linked_config';
--   SELECT count(*) FROM information_schema.tables WHERE table_name = 'activity_lead_links';
--   SELECT column_name FROM information_schema.columns WHERE table_name = 'leads' AND column_name = 'title';
--   SELECT count(*) FROM reference_data WHERE category = 'lead_stage';
--   SELECT column_name FROM information_schema.columns WHERE table_name = 'organizations' AND column_name = 'asset_class';
-- =====================================================================

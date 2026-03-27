-- =============================================================================
-- Echo 2.0 — Full Database Schema
-- Based on PRD v1.0, March 2026
-- Target: Supabase (PostgreSQL 15+)
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- for fuzzy text search / duplicate detection

-- =============================================================================
-- REFERENCE DATA (lookup tables)
-- All dropdown values are stored here, not hardcoded.
-- =============================================================================

CREATE TABLE reference_data (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    category        TEXT NOT NULL,           -- e.g. 'organization_type', 'activity_type'
    value           TEXT NOT NULL,
    label           TEXT NOT NULL,           -- display label
    parent_value    TEXT,                    -- for subtypes (e.g. activity subtype → parent type)
    display_order   INT NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(category, value)
);

-- Seed: Organization Type
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('organization_type', 'pension_fund', 'Pension Fund', 1),
    ('organization_type', 'endowment', 'Endowment', 2),
    ('organization_type', 'foundation', 'Foundation', 3),
    ('organization_type', 'sovereign_wealth_fund', 'Sovereign Wealth Fund', 4),
    ('organization_type', 'family_office', 'Family Office', 5),
    ('organization_type', 'insurance_company', 'Insurance Company', 6),
    ('organization_type', 'fund_of_funds', 'Fund of Funds', 7),
    ('organization_type', 'consultant', 'Consultant', 8),
    ('organization_type', 'placement_agent', 'Placement Agent', 9),
    ('organization_type', 'bank_wealth_manager', 'Bank/Wealth Manager', 10),
    ('organization_type', 'ria', 'RIA', 11),
    ('organization_type', 'government', 'Government', 12),
    ('organization_type', 'corporate', 'Corporate', 13),
    ('organization_type', 'other', 'Other', 14);

-- Seed: Relationship Type
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('relationship_type', 'client', 'Client', 1),
    ('relationship_type', 'prospect', 'Prospect', 2),
    ('relationship_type', 'other', 'Other', 3);

-- Seed: Activity Type
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('activity_type', 'call', 'Call', 1),
    ('activity_type', 'meeting', 'Meeting', 2),
    ('activity_type', 'note', 'Note', 3),
    ('activity_type', 'email', 'Email', 4),
    ('activity_type', 'conference', 'Conference / Event', 5),
    ('activity_type', 'webinar', 'Webinar', 6);

-- Seed: Activity Subtype (scoped to parent type)
INSERT INTO reference_data (category, value, label, parent_value, display_order) VALUES
    ('activity_subtype', 'in_person', 'In-Person', 'meeting', 1),
    ('activity_subtype', 'video_call', 'Video Call', 'meeting', 2),
    ('activity_subtype', 'conference_call', 'Conference Call', 'meeting', 3),
    ('activity_subtype', 'pipeline_call', 'Pipeline Call', 'meeting', 4),
    ('activity_subtype', 'site_visit', 'Site Visit', 'meeting', 5);

-- Seed: Lead Stage (advisory stages scoped with parent_value='advisory')
INSERT INTO reference_data (category, value, label, parent_value, display_order) VALUES
    ('lead_stage', 'exploratory', 'Open [Exploratory]', 'advisory', 1),
    ('lead_stage', 'radar', 'Open [Radar]', 'advisory', 2),
    ('lead_stage', 'focus', 'Open [Focus]', 'advisory', 3),
    ('lead_stage', 'verbal_mandate', 'Open [Verbal Mandate - In Contract]', 'advisory', 4),
    ('lead_stage', 'won', 'Inactive [Won Mandate – Aksia Client]', 'advisory', 5),
    ('lead_stage', 'lost_dropped_out', 'Inactive [Lost – Aksia Dropped Out]', 'advisory', 6),
    ('lead_stage', 'lost_selected_other', 'Inactive [Lost – Selected Someone Else]', 'advisory', 7),
    ('lead_stage', 'lost_nobody_hired', 'Inactive [Lost – Nobody Hired]', 'advisory', 8);

-- Seed: Lead Stage (fundraise stages scoped with parent_value='fundraise')
INSERT INTO reference_data (category, value, label, parent_value, display_order) VALUES
    ('lead_stage', 'target_identified', 'Target Identified', 'fundraise', 1),
    ('lead_stage', 'intro_scheduled', 'Intro Scheduled', 'fundraise', 2),
    ('lead_stage', 'initial_meeting_complete', 'Initial Meeting Complete', 'fundraise', 3),
    ('lead_stage', 'ddq_materials_sent', 'DDQ / Materials Sent', 'fundraise', 4),
    ('lead_stage', 'due_diligence', 'Due Diligence', 'fundraise', 5),
    ('lead_stage', 'ic_review', 'IC Review', 'fundraise', 6),
    ('lead_stage', 'soft_circle', 'Soft Circle', 'fundraise', 7),
    ('lead_stage', 'legal_docs', 'Legal / Docs', 'fundraise', 8),
    ('lead_stage', 'closed', 'Closed', 'fundraise', 9),
    ('lead_stage', 'declined', 'Declined', 'fundraise', 10);

-- Seed: Lead Type
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('lead_type', 'advisory', 'Advisory', 1),
    ('lead_type', 'product', 'Product', 2),
    ('lead_type', 'fundraise', 'Fundraise', 3);

-- Seed: Lead Relationship Type
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('lead_relationship_type', 'new', 'New', 1),
    ('lead_relationship_type', 'upsell', 'Upsell', 2),
    ('lead_relationship_type', 'cross_sell', 'Cross-sell', 3),
    ('lead_relationship_type', 'contract_extension', 'Contract Extension', 4),
    ('lead_relationship_type', 're_up', 'Re-Up', 5);

-- Seed: Service Type
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('service_type', 'advisory', 'Advisory', 1),
    ('service_type', 'discretionary', 'Discretionary', 2),
    ('service_type', 'research', 'Research', 3),
    ('service_type', 'reporting', 'Reporting', 4),
    ('service_type', 'project', 'Project', 5),
    ('service_type', 'product', 'Product', 6);

-- Seed: Asset Class
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('asset_class', 'hf', 'HF', 1),
    ('asset_class', 'pe', 'PE', 2),
    ('asset_class', 'pc', 'PC', 3),
    ('asset_class', 're', 'RE', 4),
    ('asset_class', 'ra', 'RA', 5),
    ('asset_class', 'co_invest_re', 'Co-Invest RE', 6),
    ('asset_class', 'co_invest_pe', 'Co-Invest PE', 7),
    ('asset_class', 'co_invest_ra', 'Co-Invest RA', 8),
    ('asset_class', 'co_invest_pc', 'Co-Invest PC', 9),
    ('asset_class', 'apc_lux', 'APC Lux', 10),
    ('asset_class', 'offshore_cape', 'Offshore CAPE', 11),
    ('asset_class', 'offshore_capix', 'Offshore CAPIX', 12),
    ('asset_class', 'cape', 'CAPE', 13),
    ('asset_class', 'capix', 'CAPIX', 14);

-- Seed: Fund Prospect Stage
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('fund_prospect_stage', 'target_identified', 'Target Identified', 1),
    ('fund_prospect_stage', 'intro_scheduled', 'Intro Scheduled', 2),
    ('fund_prospect_stage', 'initial_meeting_complete', 'Initial Meeting Complete', 3),
    ('fund_prospect_stage', 'ddq_materials_sent', 'DDQ / Materials Sent', 4),
    ('fund_prospect_stage', 'due_diligence', 'Due Diligence', 5),
    ('fund_prospect_stage', 'ic_review', 'IC Review', 6),
    ('fund_prospect_stage', 'soft_circle', 'Soft Circle', 7),
    ('fund_prospect_stage', 'legal_docs', 'Legal / Docs', 8),
    ('fund_prospect_stage', 'closed', 'Closed', 9),
    ('fund_prospect_stage', 'declined', 'Declined', 10);

-- Seed: Fund Prospect Decline Reason
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('decline_reason', 'strategy_fit', 'Strategy/Fit', 1),
    ('decline_reason', 'timing', 'Timing', 2),
    ('decline_reason', 'valuation', 'Valuation', 3),
    ('decline_reason', 'competitive', 'Competitive', 4),
    ('decline_reason', 'no_response', 'No Response', 5),
    ('decline_reason', 'internal_constraints', 'Internal Constraints', 6),
    ('decline_reason', 'other', 'Other', 7);

-- Seed: Pricing Proposal
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('pricing_proposal', 'formal', 'Formal', 1),
    ('pricing_proposal', 'informal', 'Informal', 2),
    ('pricing_proposal', 'no_proposal', 'No Proposal Made', 3);

-- Seed: RFP Status
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('rfp_status', 'expected', 'Expected', 1),
    ('rfp_status', 'in_progress', 'In-Progress', 2),
    ('rfp_status', 'submitted', 'Submitted', 3),
    ('rfp_status', 'not_applicable', 'Not Applicable', 4);

-- Seed: Risk Weight
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('risk_weight', 'high', 'High', 1),
    ('risk_weight', 'medium', 'Medium', 2),
    ('risk_weight', 'low', 'Low', 3);

-- Seed: Fee Arrangement Frequency
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('fee_frequency', 'monthly', 'Monthly', 1),
    ('fee_frequency', 'quarterly', 'Quarterly', 2),
    ('fee_frequency', 'semi_annual', 'Semi-Annual', 3),
    ('fee_frequency', 'annual', 'Annual', 4);

-- Seed: Fee Arrangement Status
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('fee_status', 'active', 'Active', 1),
    ('fee_status', 'inactive', 'Inactive', 2);

-- Seed: Task Status
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('task_status', 'open', 'Open', 1),
    ('task_status', 'in_progress', 'In Progress', 2),
    ('task_status', 'complete', 'Complete', 3),
    ('task_status', 'cancelled', 'Cancelled', 4);

-- Seed: Share Class (Fund Prospect)
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('share_class', 'domestic', 'Domestic', 1),
    ('share_class', 'offshore', 'Offshore', 2);

-- Seed: Distribution List Type
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('distribution_list_type', 'publication', 'Publication', 1),
    ('distribution_list_type', 'newsletter', 'Newsletter', 2),
    ('distribution_list_type', 'fund', 'Fund', 3),
    ('distribution_list_type', 'event', 'Event', 4),
    ('distribution_list_type', 'custom', 'Custom', 5);

-- Seed: Brand
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('brand', 'aksia', 'Aksia', 1),
    ('brand', 'acpm', 'ACPM', 2);

-- Seed: Country (abbreviated — full ISO list should be loaded separately)
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('country', 'US', 'United States', 1),
    ('country', 'GB', 'United Kingdom', 2),
    ('country', 'CA', 'Canada', 3),
    ('country', 'DE', 'Germany', 4),
    ('country', 'FR', 'France', 5),
    ('country', 'JP', 'Japan', 6),
    ('country', 'AU', 'Australia', 7),
    ('country', 'CH', 'Switzerland', 8),
    ('country', 'SG', 'Singapore', 9),
    ('country', 'HK', 'Hong Kong', 10);

-- Seed: Coverage Region
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('coverage_region', 'americas', 'Americas', 1),
    ('coverage_region', 'emea', 'EMEA', 2),
    ('coverage_region', 'apac', 'APAC', 3);

-- Seed: LP Type (mirrors org type but maintained separately per PRD)
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('lp_type', 'pension_fund', 'Pension Fund', 1),
    ('lp_type', 'endowment', 'Endowment', 2),
    ('lp_type', 'foundation', 'Foundation', 3),
    ('lp_type', 'sovereign_wealth_fund', 'Sovereign Wealth Fund', 4),
    ('lp_type', 'family_office', 'Family Office', 5),
    ('lp_type', 'insurance', 'Insurance', 6),
    ('lp_type', 'fund_of_funds', 'Fund of Funds', 7),
    ('lp_type', 'ria', 'RIA', 8);

-- Seed: Person-Org Link Type
INSERT INTO reference_data (category, value, label, display_order) VALUES
    ('person_org_link_type', 'primary', 'Primary', 1),
    ('person_org_link_type', 'secondary', 'Secondary', 2),
    ('person_org_link_type', 'former', 'Former', 3);

-- =============================================================================
-- USERS
-- =============================================================================

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entra_id        TEXT UNIQUE NOT NULL,       -- Microsoft Entra Object ID
    email           TEXT UNIQUE NOT NULL,
    display_name    TEXT NOT NULL,
    first_name      TEXT,
    last_name       TEXT,
    role            TEXT NOT NULL DEFAULT 'standard_user'
                        CHECK (role IN ('admin', 'legal', 'rfp_team', 'standard_user', 'read_only')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- ORGANIZATIONS
-- =============================================================================

CREATE TABLE organizations (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_name            TEXT NOT NULL,
    short_name              TEXT,
    relationship_type       TEXT NOT NULL,           -- FK to reference_data('relationship_type')
    organization_type       TEXT NOT NULL,            -- FK to reference_data('organization_type')
    team_distribution_email TEXT,                     -- visible when relationship = client
    aum_mn                  NUMERIC(15, 2),
    website                 TEXT,
    country                 TEXT,
    city                    TEXT,
    state_province          TEXT,
    street_address          TEXT,
    postal_code             TEXT,

    -- Client Questionnaire (visible when relationship = client)
    questionnaire_filled_by     UUID REFERENCES users(id),
    questionnaire_date          DATE,
    client_discloses_info       BOOLEAN DEFAULT FALSE,
    overall_aum_mn              NUMERIC(15, 2),
    aum_as_of_date              DATE,
    aum_source                  TEXT,
    hf_target_allocation_pct    NUMERIC(5, 2),
    pe_target_allocation_pct    NUMERIC(5, 2),
    pc_target_allocation_pct    NUMERIC(5, 2),
    re_target_allocation_pct    NUMERIC(5, 2),
    ra_target_allocation_pct    NUMERIC(5, 2),
    target_allocation_source    TEXT,

    -- Confidentiality
    rfp_hold                BOOLEAN NOT NULL DEFAULT FALSE,
    nda_signed              BOOLEAN DEFAULT FALSE,       -- synced from Ostrako
    nda_expiration          BOOLEAN DEFAULT FALSE,       -- synced from Ostrako
    nda_expiration_date     DATE,                        -- synced from Ostrako

    -- Other IDs
    backstop_company_id     TEXT,
    ostrako_id              TEXT,

    -- System fields
    is_archived             BOOLEAN NOT NULL DEFAULT FALSE,
    created_by              UUID REFERENCES users(id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_organizations_name ON organizations USING gin (company_name gin_trgm_ops);
CREATE INDEX idx_organizations_relationship ON organizations (relationship_type);
CREATE INDEX idx_organizations_type ON organizations (organization_type);
CREATE INDEX idx_organizations_country ON organizations (country);
CREATE INDEX idx_organizations_ostrako ON organizations (ostrako_id);

-- =============================================================================
-- PEOPLE
-- =============================================================================

CREATE TABLE people (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    first_name              TEXT NOT NULL,
    last_name               TEXT NOT NULL,
    email                   TEXT,
    phone                   TEXT,
    job_title               TEXT,
    asset_classes_of_interest TEXT[],          -- array of asset class values
    coverage_owner          UUID REFERENCES users(id),
    do_not_contact          BOOLEAN NOT NULL DEFAULT FALSE,
    legal_compliance_notices BOOLEAN NOT NULL DEFAULT FALSE,

    -- System fields
    is_archived             BOOLEAN NOT NULL DEFAULT FALSE,
    created_by              UUID REFERENCES users(id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_people_name ON people USING gin ((first_name || ' ' || last_name) gin_trgm_ops);
CREATE INDEX idx_people_email ON people (email);
CREATE INDEX idx_people_coverage ON people (coverage_owner);

-- =============================================================================
-- PERSON ↔ ORGANIZATION LINKS
-- =============================================================================

CREATE TABLE person_organization_links (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    person_id       UUID NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    link_type       TEXT NOT NULL DEFAULT 'primary'
                        CHECK (link_type IN ('primary', 'secondary', 'former')),
    job_title_at_org TEXT,
    start_date      DATE,           -- when the person joined this org
    end_date        DATE,           -- when the person left (set on primary org change)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(person_id, organization_id)
);

CREATE INDEX idx_pol_person ON person_organization_links (person_id);
CREATE INDEX idx_pol_org ON person_organization_links (organization_id);

-- =============================================================================
-- ACTIVITIES
-- =============================================================================

CREATE TABLE activities (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title               TEXT,
    effective_date      DATE NOT NULL,
    activity_type       TEXT NOT NULL,           -- FK to reference_data('activity_type')
    subtype             TEXT,                    -- FK to reference_data('activity_subtype')
    author_id           UUID NOT NULL REFERENCES users(id),
    details             TEXT NOT NULL,           -- rich text body, up to 1M chars
    follow_up_required  BOOLEAN NOT NULL DEFAULT FALSE,
    follow_up_date      DATE,
    follow_up_notes     TEXT,
    fund_tags           UUID[],                  -- array of fund IDs
    notify_user_ids     UUID[],                  -- users to notify on save

    -- System fields
    is_archived         BOOLEAN NOT NULL DEFAULT FALSE,
    created_by          UUID REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_activities_date ON activities (effective_date DESC);
CREATE INDEX idx_activities_type ON activities (activity_type);
CREATE INDEX idx_activities_author ON activities (author_id);
CREATE INDEX idx_activities_details_fts ON activities USING gin (to_tsvector('english', details));

-- =============================================================================
-- ACTIVITY ↔ ORGANIZATION LINKS
-- =============================================================================

CREATE TABLE activity_organization_links (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    activity_id     UUID NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(activity_id, organization_id)
);

CREATE INDEX idx_aol_activity ON activity_organization_links (activity_id);
CREATE INDEX idx_aol_org ON activity_organization_links (organization_id);

-- =============================================================================
-- ACTIVITY ↔ PEOPLE LINKS
-- =============================================================================

CREATE TABLE activity_people_links (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    activity_id UUID NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    person_id   UUID NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(activity_id, person_id)
);

CREATE INDEX idx_apl_activity ON activity_people_links (activity_id);
CREATE INDEX idx_apl_person ON activity_people_links (person_id);

-- =============================================================================
-- LEADS (Advisory Pipeline)
-- =============================================================================

CREATE TABLE leads (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id         UUID NOT NULL REFERENCES organizations(id),
    start_date              DATE NOT NULL DEFAULT CURRENT_DATE,
    end_date                DATE,
    rating                  TEXT NOT NULL DEFAULT 'exploratory',  -- lead stage
    service_type            TEXT,                -- required at Radar+
    asset_classes           TEXT[],              -- required at Radar+
    relationship            TEXT,                -- required at Exploratory+; New/Upsell/etc.
    aksia_owner_id          UUID REFERENCES users(id),  -- required at Exploratory+
    source                  TEXT,                -- required at Radar+, max 100 chars
    summary                 TEXT,                -- max 200 chars

    -- Focus+ fields
    pricing_proposal        TEXT,
    pricing_proposal_details TEXT,
    expected_decision_date  DATE,
    expected_revenue        NUMERIC(15, 2),
    expected_revenue_notes  TEXT,
    expected_yr1_flar       NUMERIC(15, 2),
    expected_longterm_flar  NUMERIC(15, 2),
    previous_flar           NUMERIC(15, 2),      -- required when relationship = extension/re-up
    rfp_status              TEXT,
    rfp_expected_date       DATE,
    risk_weight             TEXT,
    next_steps              TEXT,
    next_steps_date         DATE,

    -- Verbal Mandate+ fields
    legacy_onboarding       BOOLEAN,
    legacy_onboarding_holdings TEXT,
    potential_coverage      TEXT,

    -- Lead type: advisory (default), product, fundraise
    lead_type               TEXT NOT NULL DEFAULT 'advisory',

    -- Fundraise/product fields (populated when lead_type IN ('fundraise', 'product'))
    fund_id                 UUID REFERENCES funds(id),
    share_class             TEXT,                    -- domestic/offshore; required for fundraise
    decline_reason          TEXT,                    -- required when rating = declined
    target_allocation_mn    NUMERIC(15, 2),
    soft_circle_mn          NUMERIC(15, 2),
    hard_circle_mn          NUMERIC(15, 2),
    probability_pct         INT CHECK (probability_pct >= 0 AND probability_pct <= 100),
    stage_entry_date        DATE DEFAULT CURRENT_DATE,

    -- System fields
    is_archived             BOOLEAN NOT NULL DEFAULT FALSE,
    created_by              UUID REFERENCES users(id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_leads_org ON leads (organization_id);
CREATE INDEX idx_leads_stage ON leads (rating);
CREATE INDEX idx_leads_owner ON leads (aksia_owner_id);
CREATE INDEX idx_leads_service ON leads (service_type);
CREATE INDEX idx_leads_type ON leads (lead_type);

-- =============================================================================
-- CONTRACTS
-- =============================================================================

CREATE TABLE contracts (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id         UUID NOT NULL REFERENCES organizations(id),
    originating_lead_id     UUID NOT NULL REFERENCES leads(id),
    start_date              DATE NOT NULL DEFAULT CURRENT_DATE,
    service_type            TEXT NOT NULL,
    asset_classes           TEXT[] NOT NULL,
    client_coverage         TEXT,
    summary                 TEXT,
    actual_revenue          NUMERIC(15, 2) NOT NULL,
    inflation_provision     TEXT,
    escalator_clause        TEXT,

    -- System fields
    is_archived             BOOLEAN NOT NULL DEFAULT FALSE,
    created_by              UUID REFERENCES users(id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_contracts_org ON contracts (organization_id);
CREATE INDEX idx_contracts_lead ON contracts (originating_lead_id);

-- =============================================================================
-- FUNDS (reference table)
-- =============================================================================

CREATE TABLE funds (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fund_name       TEXT NOT NULL,
    ticker          TEXT NOT NULL UNIQUE,
    brand           TEXT NOT NULL,              -- Aksia or ACPM
    asset_class     TEXT NOT NULL,
    target_raise_mn NUMERIC(15, 2),
    vintage_year    INT,
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    offshore_feeder BOOLEAN NOT NULL DEFAULT FALSE,
    custodian       TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed the four initial funds
INSERT INTO funds (fund_name, ticker, brand, asset_class, offshore_feeder, custodian) VALUES
    ('Aksia Private Credit Fund', 'APC', 'Aksia', 'Private Credit', TRUE, 'Aksia (offshore) / TBD (domestic)'),
    ('AC Private Markets – Credit', 'CAPIX', 'ACPM', 'Private Credit', TRUE, 'Aksia (offshore) / Calamos (domestic)'),
    ('AC Private Markets – Equity', 'CAPVX', 'ACPM', 'Private Equity', TRUE, 'Aksia (offshore) / Calamos (domestic)'),
    ('AC Private Markets – Hedge', 'HEDGX', 'ACPM', 'Hedge Funds', TRUE, 'Aksia (offshore) / Calamos (domestic)');

-- =============================================================================
-- FUND PROSPECTS
-- =============================================================================

CREATE TABLE fund_prospects (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id     UUID NOT NULL REFERENCES organizations(id),
    fund_id             UUID NOT NULL REFERENCES funds(id),
    share_class         TEXT NOT NULL CHECK (share_class IN ('domestic', 'offshore')),
    stage               TEXT NOT NULL DEFAULT 'target_identified',
    decline_reason      TEXT,                    -- required when stage = declined
    aksia_owner_id      UUID NOT NULL REFERENCES users(id),
    target_allocation_mn NUMERIC(15, 2),
    soft_circle_mn      NUMERIC(15, 2),
    hard_circle_mn      NUMERIC(15, 2),
    probability_pct     INT CHECK (probability_pct >= 0 AND probability_pct <= 100),
    linked_lead_id      UUID REFERENCES leads(id),
    next_steps          TEXT,
    next_steps_date     DATE,
    notes               TEXT,
    stage_entry_date    DATE NOT NULL DEFAULT CURRENT_DATE,

    -- System fields
    is_archived         BOOLEAN NOT NULL DEFAULT FALSE,
    created_by          UUID REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_fp_org ON fund_prospects (organization_id);
CREATE INDEX idx_fp_fund ON fund_prospects (fund_id);
CREATE INDEX idx_fp_stage ON fund_prospects (stage);
CREATE INDEX idx_fp_owner ON fund_prospects (aksia_owner_id);

-- =============================================================================
-- DISTRIBUTION LISTS
-- =============================================================================

CREATE TABLE distribution_lists (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    list_name       TEXT NOT NULL,
    list_type       TEXT NOT NULL,              -- publication, newsletter, fund, event, custom
    brand           TEXT,                       -- Aksia or ACPM
    asset_class     TEXT,
    frequency       TEXT,
    is_official     BOOLEAN NOT NULL DEFAULT FALSE,
    is_private      BOOLEAN NOT NULL DEFAULT TRUE,  -- custom lists default to private
    owner_id        UUID REFERENCES users(id),      -- creator of custom lists
    l2_superset_of  UUID REFERENCES distribution_lists(id),  -- L2→L1 superset enforcement
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_dl_type ON distribution_lists (list_type);

-- =============================================================================
-- DISTRIBUTION LIST MEMBERS
-- =============================================================================

CREATE TABLE distribution_list_members (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    distribution_list_id UUID NOT NULL REFERENCES distribution_lists(id) ON DELETE CASCADE,
    person_id           UUID NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    coverage_owner_id   UUID REFERENCES users(id),
    joined_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    removed_at          TIMESTAMPTZ,
    removal_reason      TEXT,                    -- e.g. 'do_not_contact', 'manual', 'bounce'
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(distribution_list_id, person_id)
);

CREATE INDEX idx_dlm_list ON distribution_list_members (distribution_list_id);
CREATE INDEX idx_dlm_person ON distribution_list_members (person_id);

-- =============================================================================
-- SEND HISTORY
-- =============================================================================

CREATE TABLE send_history (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    distribution_list_id UUID NOT NULL REFERENCES distribution_lists(id),
    sent_by             UUID NOT NULL REFERENCES users(id),
    sent_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    subject             TEXT NOT NULL,
    body                TEXT,
    recipient_count     INT NOT NULL DEFAULT 0,
    recipient_snapshot  JSONB NOT NULL DEFAULT '[]',   -- static snapshot of recipients at send time
    status              TEXT NOT NULL DEFAULT 'sent',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_sh_list ON send_history (distribution_list_id);
CREATE INDEX idx_sh_sent_at ON send_history (sent_at DESC);

-- =============================================================================
-- TASKS
-- =============================================================================

CREATE TABLE tasks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title           TEXT NOT NULL,
    due_date        DATE,
    assigned_to     UUID NOT NULL REFERENCES users(id),
    status          TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open', 'in_progress', 'complete', 'cancelled')),
    notes           TEXT,
    source          TEXT NOT NULL DEFAULT 'manual',   -- 'manual' or system trigger description

    -- Polymorphic link to any record
    linked_record_type  TEXT,                   -- 'organization', 'person', 'lead', 'fund_prospect'
    linked_record_id    UUID,

    -- System fields
    is_archived     BOOLEAN NOT NULL DEFAULT FALSE,
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_tasks_assigned ON tasks (assigned_to);
CREATE INDEX idx_tasks_status ON tasks (status);
CREATE INDEX idx_tasks_due ON tasks (due_date);
CREATE INDEX idx_tasks_linked ON tasks (linked_record_type, linked_record_id);

-- =============================================================================
-- FEE ARRANGEMENTS
-- =============================================================================

CREATE TABLE fee_arrangements (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    arrangement_name TEXT NOT NULL,
    annual_value    NUMERIC(15, 2) NOT NULL,
    frequency       TEXT NOT NULL,              -- monthly, quarterly, semi_annual, annual
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    start_date      DATE NOT NULL,
    end_date        DATE,
    notes           TEXT,

    -- System fields
    is_archived     BOOLEAN NOT NULL DEFAULT FALSE,
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_fa_org ON fee_arrangements (organization_id);

-- =============================================================================
-- TAGS
-- =============================================================================

CREATE TABLE tags (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL UNIQUE,
    created_by  UUID REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_tags_name ON tags (name);

-- =============================================================================
-- RECORD TAGS (polymorphic join: tag ↔ any entity)
-- =============================================================================

CREATE TABLE record_tags (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tag_id          UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    record_type     TEXT NOT NULL,              -- 'organization', 'person', 'lead', 'fund_prospect'
    record_id       UUID NOT NULL,
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(tag_id, record_type, record_id)
);

CREATE INDEX idx_rt_tag ON record_tags (tag_id);
CREATE INDEX idx_rt_record ON record_tags (record_type, record_id);

-- =============================================================================
-- AUDIT LOG
-- =============================================================================

CREATE TABLE audit_log (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    record_type TEXT NOT NULL,
    record_id   UUID NOT NULL,
    field_name  TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    changed_by  UUID NOT NULL REFERENCES users(id),
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_record ON audit_log (record_type, record_id);
CREATE INDEX idx_audit_user ON audit_log (changed_by);
CREATE INDEX idx_audit_time ON audit_log (changed_at DESC);

-- =============================================================================
-- FIELD DEFINITIONS (EAV metadata — defines all fields per entity type)
-- =============================================================================

CREATE TABLE field_definitions (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type             TEXT NOT NULL,   -- 'organization', 'person', 'lead', 'contract', 'activity', 'task'
    field_name              TEXT NOT NULL,   -- internal name (matches DB column or EAV key)
    display_name            TEXT NOT NULL,   -- human-readable label
    field_type              TEXT NOT NULL CHECK (field_type IN (
        'text', 'number', 'date', 'boolean', 'dropdown', 'multi_select',
        'lookup', 'address', 'phone', 'currency', 'calculated', 'url',
        'email', 'textarea'
    )),
    storage_type            TEXT NOT NULL DEFAULT 'core_column'
                                CHECK (storage_type IN ('core_column', 'eav')),
    is_required             BOOLEAN NOT NULL DEFAULT FALSE,
    is_system               BOOLEAN NOT NULL DEFAULT TRUE,   -- system fields cannot be deleted
    display_order           INT NOT NULL DEFAULT 0,
    section_name            TEXT,            -- groups fields into sections on forms
    validation_rules        JSONB DEFAULT '{}',
    dropdown_category       TEXT,            -- reference_data category for dropdown/multi_select
    dropdown_options        JSONB,           -- inline options for simple dropdowns
    calculation_expression  TEXT,            -- for calculated field type
    default_value           TEXT,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    visibility_rules        JSONB DEFAULT '{}',   -- conditional show/hide logic
    grid_default_visible    BOOLEAN NOT NULL DEFAULT TRUE,
    grid_sortable           BOOLEAN NOT NULL DEFAULT TRUE,
    grid_filterable         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by              UUID REFERENCES users(id),
    UNIQUE(entity_type, field_name)
);

CREATE INDEX idx_fd_entity ON field_definitions (entity_type);
CREATE INDEX idx_fd_entity_active ON field_definitions (entity_type) WHERE is_active = TRUE;

-- =============================================================================
-- ENTITY CUSTOM VALUES (EAV storage for admin-created fields)
-- =============================================================================

CREATE TABLE entity_custom_values (
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

CREATE INDEX idx_ecv_entity ON entity_custom_values (entity_type, entity_id);
CREATE INDEX idx_ecv_field ON entity_custom_values (field_definition_id);

-- =============================================================================
-- ROLES (dynamic, multi-role permission system)
-- =============================================================================

CREATE TABLE roles (
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

-- Seed system roles
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
     '{"entities": {"organization": ["read"], "person": ["read"], "lead": ["read"], "contract": ["read"], "activity": ["read"], "task": ["read"], "distribution_list": ["read"], "document": ["read"]}, "export": true}');

-- =============================================================================
-- USER ROLES (junction table — users can have multiple roles)
-- =============================================================================

CREATE TABLE user_roles (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id         UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    assigned_by     UUID REFERENCES users(id),
    assigned_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, role_id)
);

CREATE INDEX idx_ur_user ON user_roles (user_id);
CREATE INDEX idx_ur_role ON user_roles (role_id);

-- =============================================================================
-- DOCUMENTS (attachments linked to any entity)
-- =============================================================================

CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title           TEXT NOT NULL,
    file_url        TEXT NOT NULL,
    file_type       TEXT,                -- 'pdf', 'docx', 'xlsx', 'link', etc.
    file_size       BIGINT,              -- bytes, nullable
    entity_type     TEXT NOT NULL,       -- 'organization', 'person', 'lead', 'contract'
    entity_id       UUID NOT NULL,
    uploaded_by     UUID NOT NULL REFERENCES users(id),
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_doc_entity ON documents (entity_type, entity_id);
CREATE INDEX idx_doc_uploaded_by ON documents (uploaded_by);

-- =============================================================================
-- LEAD OWNERS (junction table — leads can have multiple owners)
-- =============================================================================

CREATE TABLE lead_owners (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    is_primary      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(lead_id, user_id)
);

CREATE INDEX idx_lo_lead ON lead_owners (lead_id);
CREATE INDEX idx_lo_user ON lead_owners (user_id);

-- =============================================================================
-- HELPER: Fuzzy duplicate detection for organizations
-- =============================================================================

CREATE OR REPLACE FUNCTION check_org_name_similarity(search_name TEXT, similarity_threshold FLOAT DEFAULT 0.4)
RETURNS TABLE(id UUID, company_name TEXT, website TEXT, organization_type TEXT, relationship_type TEXT)
AS $$
BEGIN
    RETURN QUERY
    SELECT o.id, o.company_name, o.website, o.organization_type, o.relationship_type
    FROM organizations o
    WHERE o.is_archived = FALSE
      AND similarity(o.company_name, search_name) > similarity_threshold
    ORDER BY similarity(o.company_name, search_name) DESC
    LIMIT 10;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- HELPER: Fuzzy duplicate detection for people
-- =============================================================================

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
    WHERE p.is_archived = FALSE
      AND similarity(p.first_name || ' ' || p.last_name, search_first || ' ' || search_last) > similarity_threshold
    ORDER BY similarity(p.first_name || ' ' || p.last_name, search_first || ' ' || search_last) DESC
    LIMIT 10;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- HELPER: Auto-update updated_at timestamp
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to all tables with updated_at
CREATE TRIGGER trg_organizations_updated BEFORE UPDATE ON organizations FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_people_updated BEFORE UPDATE ON people FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_activities_updated BEFORE UPDATE ON activities FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_leads_updated BEFORE UPDATE ON leads FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_contracts_updated BEFORE UPDATE ON contracts FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_fund_prospects_updated BEFORE UPDATE ON fund_prospects FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_fee_arrangements_updated BEFORE UPDATE ON fee_arrangements FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_distribution_lists_updated BEFORE UPDATE ON distribution_lists FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_tasks_updated BEFORE UPDATE ON tasks FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_reference_data_updated BEFORE UPDATE ON reference_data FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_funds_updated BEFORE UPDATE ON funds FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_person_org_links_updated BEFORE UPDATE ON person_organization_links FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_field_definitions_updated BEFORE UPDATE ON field_definitions FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_entity_custom_values_updated BEFORE UPDATE ON entity_custom_values FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_roles_updated BEFORE UPDATE ON roles FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- PAGE LAYOUTS (admin-configurable view/edit page layouts)
-- =============================================================================

CREATE TABLE page_layouts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type     TEXT NOT NULL,
    layout_type     TEXT NOT NULL DEFAULT 'view',  -- 'view' or 'edit'
    sections        JSONB NOT NULL DEFAULT '[]',   -- [{name, fields: [field_name, ...]}]
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_pl_entity ON page_layouts (entity_type, layout_type);
CREATE TRIGGER trg_page_layouts_updated BEFORE UPDATE ON page_layouts FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- SAVED VIEWS (user-configurable grid column/filter/sort presets)
-- =============================================================================

CREATE TABLE saved_views (
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

CREATE INDEX idx_sv_user_entity ON saved_views (user_id, entity_type);
CREATE TRIGGER trg_saved_views_updated BEFORE UPDATE ON saved_views FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Seed: Lead Finder shared view
-- INSERT INTO saved_views (user_id, entity_type, view_name, columns, filters, sort_by, sort_dir, is_shared, is_default)
-- VALUES ('{admin_user_id}', 'organization', 'Lead Finder', '["company_name","organization_type","country","active_leads_count","relationship_type"]', '{}', 'active_leads_count', 'desc', true, false);


-- =====================================================================
-- Phase 5: Rename is_archived → is_deleted (Change 14)
-- =====================================================================

ALTER TABLE organizations RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE people RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE activities RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE leads RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE contracts RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE tasks RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE person_organization_links RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE activity_organization_links RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE activity_people_links RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE fee_arrangements RENAME COLUMN is_archived TO is_deleted;
ALTER TABLE record_tags RENAME COLUMN is_archived TO is_deleted;
-- documents table already uses is_deleted — no rename needed
-- distribution_lists.is_active stays as-is — it's a status field, not a soft-delete flag


-- =====================================================================
-- Phase 5: Duplicate Suppressions table (Change 15)
-- =====================================================================

CREATE TABLE duplicate_suppressions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type     TEXT NOT NULL,
    record_id_a     UUID NOT NULL,
    record_id_b     UUID NOT NULL,
    suppressed_by   UUID NOT NULL REFERENCES users(id),
    suppressed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(entity_type, record_id_a, record_id_b)
);
CREATE INDEX idx_dup_supp_entity ON duplicate_suppressions (entity_type);


-- =====================================================================
-- Phase 6: View Configurations (admin-configurable view settings)
-- =====================================================================

CREATE TABLE view_configurations (
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
CREATE INDEX idx_vc_key ON view_configurations (view_key);

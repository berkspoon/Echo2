"""Seed field_definitions table with metadata for all existing entity columns.

Run:  cd echo2 && python -m scripts.seed_field_definitions [--force]
"""

import argparse
import sys
from db.client import get_supabase


# ---------------------------------------------------------------------------
# Field definition records, one per existing column per entity type.
# storage_type is 'core_column' for all existing fields.
# Fields are ordered by section_name + display_order.
# ---------------------------------------------------------------------------

ORGANIZATION_FIELDS = [
    # Basic Information
    {"field_name": "company_name", "display_name": "Company Name", "field_type": "text", "is_required": True, "section_name": "Basic Information", "display_order": 1},
    {"field_name": "short_name", "display_name": "Short Name", "field_type": "text", "section_name": "Basic Information", "display_order": 2},
    {"field_name": "relationship_type", "display_name": "Relationship Type", "field_type": "dropdown", "is_required": True, "dropdown_category": "relationship_type", "section_name": "Basic Information", "display_order": 3},
    {"field_name": "organization_type", "display_name": "Organization Type", "field_type": "dropdown", "is_required": True, "dropdown_category": "organization_type", "section_name": "Basic Information", "display_order": 4},
    {"field_name": "aum_mn", "display_name": "AUM ($M)", "field_type": "currency", "section_name": "Basic Information", "display_order": 5},
    {"field_name": "website", "display_name": "Website", "field_type": "url", "section_name": "Basic Information", "display_order": 6},
    {"field_name": "team_distribution_email", "display_name": "Team Distribution Email", "field_type": "email", "section_name": "Basic Information", "display_order": 7, "visibility_rules": {"when": "relationship_type", "equals": "client"}},
    {"field_name": "asset_class", "display_name": "Asset Class", "field_type": "multi_select", "dropdown_category": "org_asset_class", "section_name": "Basic Information", "display_order": 7.5, "visibility_rules": {"when": "relationship_type", "equals": "client"}},
    {"field_name": "product_funds", "display_name": "Product Funds", "field_type": "multi_select", "dropdown_category": "org_product_fund", "section_name": "Basic Information", "display_order": 7.6, "visibility_rules": {"when": "asset_class", "in": ["product"]}},
    # feedback: [padelsbach] text_list field type for aliases/nicknames
    {"field_name": "nicknames", "display_name": "Nicknames / Aliases", "field_type": "text_list", "section_name": "Basic Information", "display_order": 8, "storage_type": "eav", "is_system": False, "grid_default_visible": False},
    # Address
    {"field_name": "country", "display_name": "Country", "field_type": "dropdown", "dropdown_category": "country", "section_name": "Address", "display_order": 10},
    {"field_name": "city", "display_name": "City", "field_type": "text", "section_name": "Address", "display_order": 11},
    {"field_name": "state_province", "display_name": "State / Province", "field_type": "text", "section_name": "Address", "display_order": 12},
    {"field_name": "street_address", "display_name": "Street Address", "field_type": "text", "section_name": "Address", "display_order": 13},
    {"field_name": "postal_code", "display_name": "Postal Code", "field_type": "text", "section_name": "Address", "display_order": 14},
    # Confidentiality
    {"field_name": "rfp_hold", "display_name": "RFP Hold", "field_type": "boolean", "section_name": "Confidentiality", "display_order": 20},
    {"field_name": "nda_signed", "display_name": "NDA Signed", "field_type": "boolean", "section_name": "Confidentiality", "display_order": 21},
    {"field_name": "nda_expiration", "display_name": "NDA Has Expiration", "field_type": "boolean", "section_name": "Confidentiality", "display_order": 22},
    {"field_name": "nda_expiration_date", "display_name": "NDA Expiration Date", "field_type": "date", "section_name": "Confidentiality", "display_order": 23, "visibility_rules": {"when": "nda_expiration", "equals": True}},
    # Client Questionnaire
    {"field_name": "questionnaire_filled_by", "display_name": "Questionnaire Filled By", "field_type": "lookup", "section_name": "Client Questionnaire", "display_order": 30, "visibility_rules": {"when": "relationship_type", "equals": "client"}},
    {"field_name": "questionnaire_date", "display_name": "Questionnaire Date", "field_type": "date", "section_name": "Client Questionnaire", "display_order": 31, "visibility_rules": {"when": "relationship_type", "equals": "client"}},
    {"field_name": "client_discloses_info", "display_name": "Client Discloses Info", "field_type": "boolean", "section_name": "Client Questionnaire", "display_order": 32, "visibility_rules": {"when": "relationship_type", "equals": "client"}},
    {"field_name": "overall_aum_mn", "display_name": "Overall AUM ($M)", "field_type": "currency", "section_name": "Client Questionnaire", "display_order": 33, "visibility_rules": {"when": "client_discloses_info", "equals": True}},
    {"field_name": "aum_as_of_date", "display_name": "AUM As-Of Date", "field_type": "date", "section_name": "Client Questionnaire", "display_order": 34, "visibility_rules": {"when": "client_discloses_info", "equals": True}},
    {"field_name": "aum_source", "display_name": "AUM Source", "field_type": "text", "section_name": "Client Questionnaire", "display_order": 35, "visibility_rules": {"when": "client_discloses_info", "equals": True}},
    {"field_name": "hf_target_allocation_pct", "display_name": "HF Target Allocation %", "field_type": "number", "section_name": "Client Questionnaire", "display_order": 36, "visibility_rules": {"when": "client_discloses_info", "equals": True}},
    {"field_name": "pe_target_allocation_pct", "display_name": "PE Target Allocation %", "field_type": "number", "section_name": "Client Questionnaire", "display_order": 37, "visibility_rules": {"when": "client_discloses_info", "equals": True}},
    {"field_name": "pc_target_allocation_pct", "display_name": "PC Target Allocation %", "field_type": "number", "section_name": "Client Questionnaire", "display_order": 38, "visibility_rules": {"when": "client_discloses_info", "equals": True}},
    {"field_name": "re_target_allocation_pct", "display_name": "RE Target Allocation %", "field_type": "number", "section_name": "Client Questionnaire", "display_order": 39, "visibility_rules": {"when": "client_discloses_info", "equals": True}},
    {"field_name": "ra_target_allocation_pct", "display_name": "RA Target Allocation %", "field_type": "number", "section_name": "Client Questionnaire", "display_order": 40, "visibility_rules": {"when": "client_discloses_info", "equals": True}},
    {"field_name": "target_allocation_source", "display_name": "Target Allocation Source", "field_type": "text", "section_name": "Client Questionnaire", "display_order": 41, "visibility_rules": {"when": "client_discloses_info", "equals": True}},
    # Legacy IDs
    {"field_name": "backstop_company_id", "display_name": "Backstop Company ID", "field_type": "text", "section_name": "Legacy IDs", "display_order": 50, "grid_default_visible": False},
    {"field_name": "ostrako_id", "display_name": "Ostrako ID", "field_type": "text", "section_name": "Legacy IDs", "display_order": 51, "grid_default_visible": False},
]

PERSON_FIELDS = [
    # Basic Information
    {"field_name": "first_name", "display_name": "First Name", "field_type": "text", "is_required": True, "section_name": "Basic Information", "display_order": 1},
    {"field_name": "last_name", "display_name": "Last Name", "field_type": "text", "is_required": True, "section_name": "Basic Information", "display_order": 2},
    {"field_name": "email", "display_name": "Email", "field_type": "email", "section_name": "Basic Information", "display_order": 3},
    {"field_name": "phone", "display_name": "Phone", "field_type": "phone", "section_name": "Basic Information", "display_order": 4},
    {"field_name": "job_title", "display_name": "Job Title", "field_type": "text", "section_name": "Basic Information", "display_order": 5},
    # Relationships
    {"field_name": "coverage_owner", "display_name": "Coverage Owner", "field_type": "lookup", "section_name": "Relationships", "display_order": 10},
    {"field_name": "asset_classes_of_interest", "display_name": "Asset Classes of Interest", "field_type": "multi_select", "dropdown_category": "asset_class", "section_name": "Relationships", "display_order": 11},
    # Contact Preferences
    {"field_name": "do_not_contact", "display_name": "Do Not Contact", "field_type": "boolean", "section_name": "Contact Preferences", "display_order": 20},
    {"field_name": "legal_compliance_notices", "display_name": "Legal & Compliance Notices", "field_type": "boolean", "section_name": "Contact Preferences", "display_order": 21, "visibility_rules": {"when": "do_not_contact", "equals": False}},
]

LEAD_FIELDS = [
    # === Basic Information (always visible) ===
    {"field_name": "title", "display_name": "Title", "field_type": "text", "is_required": True, "section_name": "Basic Information", "display_order": 0},
    {"field_name": "organization_id", "display_name": "Organization", "field_type": "lookup", "is_required": True, "section_name": "Basic Information", "display_order": 1},
    {"field_name": "lead_type", "display_name": "Lead Type", "field_type": "dropdown", "is_required": True, "dropdown_category": "lead_type", "section_name": "Basic Information", "display_order": 2},
    {"field_name": "rating", "display_name": "Stage", "field_type": "dropdown", "is_required": True, "dropdown_category": "lead_stage", "section_name": "Basic Information", "display_order": 3},
    {"field_name": "start_date", "display_name": "Start Date", "field_type": "date", "section_name": "Basic Information", "display_order": 4},
    {"field_name": "relationship", "display_name": "Relationship", "field_type": "dropdown", "dropdown_category": "lead_relationship_type", "section_name": "Basic Information", "display_order": 5, "visibility_rules": {"lead_type": "service"}},
    {"field_name": "aksia_owner_id", "display_name": "Aksia Owner", "field_type": "lookup", "section_name": "Basic Information", "display_order": 6},
    {"field_name": "summary", "display_name": "Summary", "field_type": "textarea", "section_name": "Basic Information", "display_order": 7, "validation_rules": {"max": 250}},
    {"field_name": "engagement_status", "display_name": "Engagement Status", "field_type": "dropdown", "dropdown_category": "engagement_status", "section_name": "Basic Information", "display_order": 8},
    # === Overview ===
    {"field_name": "coverage_office", "display_name": "Coverage Office", "field_type": "dropdown", "dropdown_category": "coverage_office", "section_name": "Overview", "display_order": 10},
    {"field_name": "service_type", "display_name": "Service Type", "field_type": "dropdown", "dropdown_category": "service_type", "section_name": "Overview", "display_order": 11, "visibility_rules": {"min_stage": 2}},
    {"field_name": "service_subtype", "display_name": "Service Subtype", "field_type": "dropdown", "dropdown_category": "service_subtype", "section_name": "Overview", "display_order": 12, "visibility_rules": {"min_stage": 2}},
    {"field_name": "asset_classes", "display_name": "Asset Classes", "field_type": "multi_select", "dropdown_category": "asset_class", "section_name": "Overview", "display_order": 13, "visibility_rules": {"min_stage": 2}},
    {"field_name": "source", "display_name": "Source", "field_type": "text", "section_name": "Overview", "display_order": 14, "visibility_rules": {"min_stage": 2}, "suggestion_rules": {"min_stage": 2}},
    {"field_name": "includes_product_allocation", "display_name": "Includes Product Allocation", "field_type": "boolean", "section_name": "Overview", "display_order": 15, "visibility_rules": {"lead_type": "service"}},
    {"field_name": "includes_max_access", "display_name": "Includes MAX Access", "field_type": "boolean", "section_name": "Overview", "display_order": 16, "visibility_rules": {"lead_type": "product"}},
    # === Timeline (auto-populated engagement status dates) ===
    {"field_name": "prospect_contacted_date", "display_name": "Prospect Contacted Date", "field_type": "date", "section_name": "Timeline", "display_order": 70},
    {"field_name": "prospect_responded_date", "display_name": "Prospect Responded Date", "field_type": "date", "section_name": "Timeline", "display_order": 71},
    {"field_name": "initial_meeting_date", "display_name": "Initial Meeting Date", "field_type": "date", "section_name": "Timeline", "display_order": 72},
    {"field_name": "initial_meeting_complete_date", "display_name": "Initial Meeting Complete Date", "field_type": "date", "section_name": "Timeline", "display_order": 73},
    # === Focus+ Fields ===
    {"field_name": "risk_weight", "display_name": "Probability of Close", "field_type": "dropdown", "dropdown_category": "risk_weight", "section_name": "Focus", "display_order": 20, "visibility_rules": {"min_stage": 3}},
    {"field_name": "indicative_size_low", "display_name": "Indicative Size (Low)", "field_type": "currency", "section_name": "Focus", "display_order": 21, "visibility_rules": {"min_stage": 3, "when": "service_type", "in": ["product", "investment_management"]}},
    {"field_name": "indicative_size_high", "display_name": "Indicative Size (High)", "field_type": "currency", "section_name": "Focus", "display_order": 22, "visibility_rules": {"min_stage": 3, "when": "service_type", "in": ["product", "investment_management"]}},
    {"field_name": "expected_contract_start_date", "display_name": "Expected Contract Start Date", "field_type": "date", "section_name": "Focus", "display_order": 23, "visibility_rules": {"min_stage": 3}},
    {"field_name": "revenue_currency", "display_name": "Revenue Currency", "field_type": "dropdown", "dropdown_category": "revenue_currency", "section_name": "Focus", "display_order": 24, "visibility_rules": {"min_stage": 3}},
    {"field_name": "expected_yr1_flar", "display_name": "Expected Yr1 FLAR", "field_type": "currency", "section_name": "Focus", "display_order": 25, "visibility_rules": {"min_stage": 3}},
    {"field_name": "expected_longterm_flar", "display_name": "Expected Long-Term FLAR", "field_type": "currency", "section_name": "Focus", "display_order": 26, "visibility_rules": {"min_stage": 3}},
    {"field_name": "previous_flar", "display_name": "Previous FLAR", "field_type": "currency", "section_name": "Focus", "display_order": 27, "visibility_rules": {"min_stage": 3, "when": "relationship", "in": ["existing_client_contract_extension"]}},
    # === Service Details (non-IM service types at Focus+) ===
    {"field_name": "expected_fee", "display_name": "Expected Fee", "field_type": "currency", "section_name": "Service Details", "display_order": 30, "visibility_rules": {"min_stage": 3, "when": "service_type", "in": ["advisory", "advisory_bps", "research", "project", "reporting"]}},
    {"field_name": "expected_revenue_notes", "display_name": "Revenue Notes", "field_type": "textarea", "section_name": "Service Details", "display_order": 31, "visibility_rules": {"min_stage": 3}},
    # === IM Details (service_type=investment_management at Focus+) ===
    {"field_name": "expected_management_fee", "display_name": "Expected Management Fee (%)", "field_type": "number", "section_name": "IM Details", "display_order": 35, "visibility_rules": {"min_stage": 3, "when": "service_type", "equals": "investment_management"}},
    {"field_name": "expected_incentive_fee", "display_name": "Expected Incentive Fee (%)", "field_type": "number", "section_name": "IM Details", "display_order": 36, "visibility_rules": {"min_stage": 3, "when": "service_type", "equals": "investment_management"}},
    {"field_name": "expected_preferred_return", "display_name": "Expected Preferred Return (%)", "field_type": "number", "section_name": "IM Details", "display_order": 37, "visibility_rules": {"min_stage": 3, "when": "service_type", "equals": "investment_management"}},
    {"field_name": "expected_catchup_pct", "display_name": "Expected Catch-Up (%)", "field_type": "number", "section_name": "IM Details", "display_order": 38, "visibility_rules": {"min_stage": 3, "when": "service_type", "equals": "investment_management"}},
    {"field_name": "expected_size", "display_name": "Expected Size", "field_type": "text", "section_name": "IM Details", "display_order": 39, "visibility_rules": {"min_stage": 3, "when": "service_type", "in": ["investment_management", "product"]}},
    {"field_name": "gp_commitment", "display_name": "GP Commitment", "field_type": "dropdown", "dropdown_category": "gp_commitment", "section_name": "IM Details", "display_order": 40, "visibility_rules": {"when": "service_type", "equals": "investment_management"}},
    {"field_name": "deployment_period", "display_name": "Deployment Period", "field_type": "dropdown", "dropdown_category": "deployment_period", "section_name": "IM Details", "display_order": 41, "visibility_rules": {"when": "service_type", "equals": "investment_management"}},
    # === Product Details (service_type=product at Focus+) ===
    {"field_name": "commitment_status", "display_name": "Commitment Status", "field_type": "dropdown", "dropdown_category": "commitment_status", "section_name": "Product Details", "display_order": 45, "visibility_rules": {"min_stage": 3, "when": "service_type", "equals": "product"}},
    {"field_name": "waystone_approved", "display_name": "Waystone Approved", "field_type": "dropdown", "dropdown_category": "waystone_approved", "section_name": "Product Details", "display_order": 46, "visibility_rules": {"when": "service_type", "equals": "product"}},
    {"field_name": "expected_fund_close", "display_name": "Expected Fund Close", "field_type": "dropdown", "dropdown_category": "expected_fund_close", "section_name": "Product Details", "display_order": 47, "visibility_rules": {"min_stage": 3, "when": "service_type", "equals": "product"}},
    # === RFP (visible based on engagement_status) ===
    {"field_name": "rfp_due_date", "display_name": "RFP Due Date", "field_type": "date", "section_name": "RFP", "display_order": 50, "visibility_rules": {"when": "engagement_status", "in": ["rfp_expected", "rfp_in_progress", "rfp_submitted"]}},
    {"field_name": "rfp_submitted_date", "display_name": "RFP Submitted Date", "field_type": "date", "section_name": "RFP", "display_order": 51, "visibility_rules": {"when": "engagement_status", "in": ["rfp_submitted"]}},
    # === Follow-Up (always visible) ===
    {"field_name": "next_steps", "display_name": "Follow-Up Notes", "field_type": "textarea", "section_name": "Follow-Up", "display_order": 55},
    {"field_name": "next_steps_date", "display_name": "Follow-Up Date", "field_type": "date", "section_name": "Follow-Up", "display_order": 56},
    # === Verbal Mandate+ ===
    {"field_name": "legacy_onboarding", "display_name": "Legacy Onboarding", "field_type": "boolean", "section_name": "Verbal Mandate", "display_order": 60, "visibility_rules": {"min_stage": 4}},
    {"field_name": "legacy_onboarding_holdings", "display_name": "Legacy Onboarding Holdings", "field_type": "textarea", "section_name": "Verbal Mandate", "display_order": 61, "visibility_rules": {"min_stage": 4, "when": "legacy_onboarding", "equals": True}},
    {"field_name": "potential_coverage", "display_name": "Potential Coverage", "field_type": "text", "section_name": "Verbal Mandate", "display_order": 62, "visibility_rules": {"min_stage": 4}},
    # === Fund & Allocation (product leads only) ===
    {"field_name": "fund_id", "display_name": "Fund", "field_type": "lookup", "is_required": True, "section_name": "Fund & Allocation", "display_order": 80, "visibility_rules": {"lead_type": "product"}},
    {"field_name": "share_class", "display_name": "Share Class", "field_type": "dropdown", "is_required": True, "dropdown_category": "share_class", "section_name": "Fund & Allocation", "display_order": 81, "visibility_rules": {"lead_type": "product"}},
    {"field_name": "target_allocation_mn", "display_name": "Target Allocation ($M)", "field_type": "currency", "section_name": "Fund & Allocation", "display_order": 82, "visibility_rules": {"lead_type": "product"}},
    {"field_name": "soft_circle_mn", "display_name": "Soft Circle ($M)", "field_type": "currency", "section_name": "Fund & Allocation", "display_order": 83, "visibility_rules": {"lead_type": "product"}},
    {"field_name": "hard_circle_mn", "display_name": "Hard Circle ($M)", "field_type": "currency", "section_name": "Fund & Allocation", "display_order": 84, "visibility_rules": {"lead_type": "product"}},
    {"field_name": "probability_pct", "display_name": "Probability %", "field_type": "number", "section_name": "Fund & Allocation", "display_order": 85, "visibility_rules": {"lead_type": "product"}, "validation_rules": {"min": 0, "max": 100}},
    {"field_name": "stage_entry_date", "display_name": "Stage Entry Date", "field_type": "date", "section_name": "Fund & Allocation", "display_order": 86, "visibility_rules": {"lead_type": "product"}},
    {"field_name": "decline_reason", "display_name": "Decline Reason", "field_type": "dropdown", "dropdown_category": "decline_reason", "section_name": "Fund & Allocation", "display_order": 87, "visibility_rules": {"lead_type": "product", "when": "rating", "equals": "declined"}},
    # === Closure / Declined (service leads) ===
    {"field_name": "end_date", "display_name": "End Date", "field_type": "date", "section_name": "Closure", "display_order": 90, "visibility_rules": {"when": "rating", "in": ["won", "did_not_win", "closed", "declined"]}},
    {"field_name": "decline_reason_code", "display_name": "Decline Reason", "field_type": "dropdown", "dropdown_category": "decline_reason_code", "section_name": "Closure", "display_order": 91, "visibility_rules": {"when": "rating", "equals": "did_not_win"}},
    {"field_name": "decline_rationale", "display_name": "Decline Rationale", "field_type": "textarea", "section_name": "Closure", "display_order": 92, "visibility_rules": {"when": "rating", "equals": "did_not_win"}, "validation_rules": {"max": 500}},
]

ACTIVITY_FIELDS = [
    {"field_name": "title", "display_name": "Title", "field_type": "text", "section_name": "Basic Information", "display_order": 1},
    {"field_name": "effective_date", "display_name": "Date", "field_type": "date", "is_required": True, "section_name": "Basic Information", "display_order": 2},
    {"field_name": "activity_type", "display_name": "Type", "field_type": "dropdown", "is_required": True, "dropdown_category": "activity_type", "section_name": "Basic Information", "display_order": 3},
    {"field_name": "subtype", "display_name": "Subtype", "field_type": "dropdown", "dropdown_category": "activity_subtype", "section_name": "Basic Information", "display_order": 4},
    {"field_name": "details", "display_name": "Details", "field_type": "textarea", "is_required": True, "section_name": "Content", "display_order": 10},
    {"field_name": "fund_tags", "display_name": "Fund Tags", "field_type": "multi_select", "section_name": "Content", "display_order": 11},
    # Follow-up
    {"field_name": "follow_up_required", "display_name": "Follow-Up Required", "field_type": "boolean", "section_name": "Follow-Up", "display_order": 20},
    {"field_name": "follow_up_date", "display_name": "Follow-Up Date", "field_type": "date", "section_name": "Follow-Up", "display_order": 21, "visibility_rules": {"when": "follow_up_required", "equals": True}},
    {"field_name": "follow_up_notes", "display_name": "Follow-Up Notes", "field_type": "textarea", "section_name": "Follow-Up", "display_order": 22, "visibility_rules": {"when": "follow_up_required", "equals": True}},
]

CONTRACT_FIELDS = [
    {"field_name": "organization_id", "display_name": "Organization", "field_type": "lookup", "is_required": True, "section_name": "Basic Information", "display_order": 1},
    {"field_name": "originating_lead_id", "display_name": "Originating Lead", "field_type": "lookup", "is_required": True, "section_name": "Basic Information", "display_order": 2},
    {"field_name": "start_date", "display_name": "Start Date", "field_type": "date", "is_required": True, "section_name": "Basic Information", "display_order": 3},
    {"field_name": "service_type", "display_name": "Service Type", "field_type": "dropdown", "is_required": True, "dropdown_category": "service_type", "section_name": "Basic Information", "display_order": 4},
    {"field_name": "asset_classes", "display_name": "Asset Classes", "field_type": "multi_select", "is_required": True, "dropdown_category": "asset_class", "section_name": "Basic Information", "display_order": 5},
    {"field_name": "actual_revenue", "display_name": "Actual Revenue", "field_type": "currency", "is_required": True, "section_name": "Financial", "display_order": 10},
    {"field_name": "client_coverage", "display_name": "Client Coverage", "field_type": "text", "section_name": "Financial", "display_order": 11},
    {"field_name": "summary", "display_name": "Summary", "field_type": "textarea", "section_name": "Details", "display_order": 20},
    {"field_name": "inflation_provision", "display_name": "Inflation Provision", "field_type": "text", "section_name": "Details", "display_order": 21, "visibility_rules": {"when": "service_type", "not_in": ["project", "product"]}},
    {"field_name": "escalator_clause", "display_name": "Escalator Clause", "field_type": "text", "section_name": "Details", "display_order": 22, "visibility_rules": {"when": "service_type", "not_in": ["project", "product"]}},
]

TASK_FIELDS = [
    {"field_name": "title", "display_name": "Title", "field_type": "text", "is_required": True, "section_name": "Basic Information", "display_order": 1},
    {"field_name": "due_date", "display_name": "Due Date", "field_type": "date", "section_name": "Basic Information", "display_order": 2},
    {"field_name": "assigned_to", "display_name": "Assigned To", "field_type": "lookup", "is_required": True, "section_name": "Basic Information", "display_order": 3},
    {"field_name": "status", "display_name": "Status", "field_type": "dropdown", "is_required": True, "dropdown_category": "task_status", "section_name": "Basic Information", "display_order": 4},
    {"field_name": "notes", "display_name": "Notes", "field_type": "textarea", "section_name": "Details", "display_order": 10},
    {"field_name": "source", "display_name": "Source", "field_type": "text", "section_name": "Details", "display_order": 11},
]

DISTRIBUTION_LIST_FIELDS = [
    # Basic Information
    {"field_name": "list_name", "display_name": "List Name", "field_type": "text", "is_required": True, "section_name": "Basic Information", "display_order": 1},
    {"field_name": "list_type", "display_name": "List Type", "field_type": "dropdown", "is_required": True, "dropdown_category": "list_type", "section_name": "Basic Information", "display_order": 2},
    {"field_name": "brand", "display_name": "Brand", "field_type": "dropdown", "dropdown_category": "brand", "section_name": "Basic Information", "display_order": 3},
    {"field_name": "asset_class", "display_name": "Asset Class", "field_type": "dropdown", "dropdown_category": "asset_class", "section_name": "Basic Information", "display_order": 4},
    {"field_name": "frequency", "display_name": "Frequency", "field_type": "dropdown", "dropdown_category": "frequency", "section_name": "Basic Information", "display_order": 5},
    {"field_name": "description", "display_name": "Description", "field_type": "textarea", "section_name": "Basic Information", "display_order": 6},
    # Settings
    {"field_name": "is_official", "display_name": "Official", "field_type": "boolean", "section_name": "Settings", "display_order": 10},
    {"field_name": "is_private", "display_name": "Private", "field_type": "boolean", "section_name": "Settings", "display_order": 11},
    {"field_name": "owner_id", "display_name": "Owner", "field_type": "lookup", "section_name": "Settings", "display_order": 12},
    # System
    {"field_name": "created_at", "display_name": "Created", "field_type": "date", "section_name": "System", "display_order": 20},
]

ALL_ENTITIES = {
    "organization": ORGANIZATION_FIELDS,
    "person": PERSON_FIELDS,
    "lead": LEAD_FIELDS,
    "activity": ACTIVITY_FIELDS,
    "contract": CONTRACT_FIELDS,
    "task": TASK_FIELDS,
    "distribution_list": DISTRIBUTION_LIST_FIELDS,
}


def seed(force: bool = False) -> None:
    sb = get_supabase()

    # Check for existing data
    existing = sb.table("field_definitions").select("id").limit(1).execute()
    if existing.data and not force:
        print("field_definitions already seeded. Use --force to re-seed.")
        return

    if force:
        print("Force mode: deleting existing field_definitions...")
        sb.table("field_definitions").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()

    total = 0
    for entity_type, fields in ALL_ENTITIES.items():
        for f in fields:
            row = {
                "entity_type": entity_type,
                "field_name": f["field_name"],
                "display_name": f["display_name"],
                "field_type": f["field_type"],
                "storage_type": f.get("storage_type", "core_column"),
                "is_required": f.get("is_required", False),
                "is_system": f.get("is_system", True),
                "display_order": int(f.get("display_order", 0)),
                "section_name": f.get("section_name"),
                "validation_rules": f.get("validation_rules", {}),
                "dropdown_category": f.get("dropdown_category"),
                "dropdown_options": f.get("dropdown_options"),
                "default_value": f.get("default_value"),
                "is_active": True,
                "visibility_rules": f.get("visibility_rules", {}),
                "suggestion_rules": f.get("suggestion_rules", {}),
                "grid_default_visible": f.get("grid_default_visible", True),
                "grid_sortable": f.get("grid_sortable", True),
                "grid_filterable": f.get("grid_filterable", True),
            }
            sb.table("field_definitions").insert(row).execute()
            total += 1
        print(f"  {entity_type}: {len(fields)} fields seeded")

    print(f"\nTotal: {total} field definitions seeded across {len(ALL_ENTITIES)} entity types.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed field_definitions table")
    parser.add_argument("--force", action="store_true", help="Re-seed (delete existing data first)")
    args = parser.parse_args()
    seed(force=args.force)

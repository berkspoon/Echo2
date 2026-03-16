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
    # Basic Information (all lead types)
    {"field_name": "organization_id", "display_name": "Organization", "field_type": "lookup", "is_required": True, "section_name": "Basic Information", "display_order": 1},
    {"field_name": "lead_type", "display_name": "Lead Type", "field_type": "dropdown", "is_required": True, "dropdown_category": "lead_type", "section_name": "Basic Information", "display_order": 2},
    {"field_name": "rating", "display_name": "Stage", "field_type": "dropdown", "is_required": True, "dropdown_category": "lead_stage", "section_name": "Basic Information", "display_order": 3},
    {"field_name": "start_date", "display_name": "Start Date", "field_type": "date", "section_name": "Basic Information", "display_order": 4},
    {"field_name": "relationship", "display_name": "Relationship", "field_type": "dropdown", "dropdown_category": "lead_relationship_type", "section_name": "Basic Information", "display_order": 5, "visibility_rules": {"min_stage": 1, "lead_type": "advisory"}},
    {"field_name": "aksia_owner_id", "display_name": "Aksia Owner", "field_type": "lookup", "section_name": "Basic Information", "display_order": 6},
    {"field_name": "summary", "display_name": "Summary", "field_type": "textarea", "section_name": "Basic Information", "display_order": 7},
    # Radar+ Fields
    {"field_name": "service_type", "display_name": "Service Type", "field_type": "dropdown", "dropdown_category": "service_type", "section_name": "Radar", "display_order": 10, "visibility_rules": {"min_stage": 2}},
    {"field_name": "asset_classes", "display_name": "Asset Classes", "field_type": "multi_select", "dropdown_category": "asset_class", "section_name": "Radar", "display_order": 11, "visibility_rules": {"min_stage": 2}},
    {"field_name": "source", "display_name": "Source", "field_type": "text", "section_name": "Radar", "display_order": 12, "visibility_rules": {"min_stage": 2}},
    # Focus+ Fields
    {"field_name": "pricing_proposal", "display_name": "Pricing Proposal", "field_type": "dropdown", "dropdown_category": "pricing_proposal", "section_name": "Focus", "display_order": 20, "visibility_rules": {"min_stage": 3}},
    {"field_name": "pricing_proposal_details", "display_name": "Pricing Proposal Details", "field_type": "textarea", "section_name": "Focus", "display_order": 21, "visibility_rules": {"min_stage": 3, "when": "pricing_proposal", "not_equals": "no_proposal"}},
    {"field_name": "expected_decision_date", "display_name": "Expected Decision Date", "field_type": "date", "section_name": "Focus", "display_order": 22, "visibility_rules": {"min_stage": 3}},
    {"field_name": "expected_revenue", "display_name": "Expected Revenue", "field_type": "currency", "section_name": "Focus", "display_order": 23, "visibility_rules": {"min_stage": 3}},
    {"field_name": "expected_revenue_notes", "display_name": "Revenue Notes", "field_type": "textarea", "section_name": "Focus", "display_order": 24, "visibility_rules": {"min_stage": 3}},
    {"field_name": "expected_yr1_flar", "display_name": "Expected Yr1 FLAR", "field_type": "currency", "section_name": "Focus", "display_order": 25, "visibility_rules": {"min_stage": 3}},
    {"field_name": "expected_longterm_flar", "display_name": "Expected Long-Term FLAR", "field_type": "currency", "section_name": "Focus", "display_order": 26, "visibility_rules": {"min_stage": 3}},
    {"field_name": "previous_flar", "display_name": "Previous FLAR", "field_type": "currency", "section_name": "Focus", "display_order": 27, "visibility_rules": {"min_stage": 3, "when": "relationship", "in": ["contract_extension", "re_up"]}},
    {"field_name": "rfp_status", "display_name": "RFP Status", "field_type": "dropdown", "dropdown_category": "rfp_status", "section_name": "Focus", "display_order": 28, "visibility_rules": {"min_stage": 3}},
    {"field_name": "rfp_expected_date", "display_name": "RFP Expected Date", "field_type": "date", "section_name": "Focus", "display_order": 29, "visibility_rules": {"min_stage": 3, "when": "rfp_status", "not_equals": "not_applicable"}},
    {"field_name": "risk_weight", "display_name": "Risk Weight", "field_type": "dropdown", "dropdown_category": "risk_weight", "section_name": "Focus", "display_order": 30, "visibility_rules": {"min_stage": 3}},
    {"field_name": "next_steps", "display_name": "Next Steps", "field_type": "textarea", "section_name": "Focus", "display_order": 31, "visibility_rules": {"min_stage": 3}},
    {"field_name": "next_steps_date", "display_name": "Next Steps Date", "field_type": "date", "section_name": "Focus", "display_order": 32, "visibility_rules": {"min_stage": 3}},
    # Verbal Mandate+ Fields
    {"field_name": "legacy_onboarding", "display_name": "Legacy Onboarding", "field_type": "boolean", "section_name": "Verbal Mandate", "display_order": 40, "visibility_rules": {"min_stage": 4}},
    {"field_name": "legacy_onboarding_holdings", "display_name": "Legacy Onboarding Holdings", "field_type": "textarea", "section_name": "Verbal Mandate", "display_order": 41, "visibility_rules": {"min_stage": 4, "when": "legacy_onboarding", "equals": True}},
    {"field_name": "potential_coverage", "display_name": "Potential Coverage", "field_type": "text", "section_name": "Verbal Mandate", "display_order": 42, "visibility_rules": {"min_stage": 4}},
    # Closure Fields (advisory)
    {"field_name": "end_date", "display_name": "End Date", "field_type": "date", "section_name": "Closure", "display_order": 50, "visibility_rules": {"when": "rating", "in": ["won", "lost_dropped_out", "lost_selected_other", "lost_nobody_hired"]}},
    # Fundraise-specific Fields
    {"field_name": "fund_id", "display_name": "Fund", "field_type": "lookup", "is_required": True, "section_name": "Fund & Allocation", "display_order": 60, "visibility_rules": {"lead_type": "fundraise"}},
    {"field_name": "share_class", "display_name": "Share Class", "field_type": "dropdown", "is_required": True, "dropdown_category": "share_class", "section_name": "Fund & Allocation", "display_order": 61, "visibility_rules": {"lead_type": "fundraise"}},
    {"field_name": "target_allocation_mn", "display_name": "Target Allocation ($M)", "field_type": "currency", "section_name": "Fund & Allocation", "display_order": 62, "visibility_rules": {"lead_type": "fundraise"}},
    {"field_name": "soft_circle_mn", "display_name": "Soft Circle ($M)", "field_type": "currency", "section_name": "Fund & Allocation", "display_order": 63, "visibility_rules": {"lead_type": "fundraise"}},
    {"field_name": "hard_circle_mn", "display_name": "Hard Circle ($M)", "field_type": "currency", "section_name": "Fund & Allocation", "display_order": 64, "visibility_rules": {"lead_type": "fundraise"}},
    {"field_name": "probability_pct", "display_name": "Probability %", "field_type": "number", "section_name": "Fund & Allocation", "display_order": 65, "visibility_rules": {"lead_type": "fundraise"}, "validation_rules": {"min": 0, "max": 100}},
    {"field_name": "stage_entry_date", "display_name": "Stage Entry Date", "field_type": "date", "section_name": "Fund & Allocation", "display_order": 66, "visibility_rules": {"lead_type": "fundraise"}},
    {"field_name": "decline_reason", "display_name": "Decline Reason", "field_type": "dropdown", "dropdown_category": "decline_reason", "section_name": "Fund & Allocation", "display_order": 67, "visibility_rules": {"lead_type": "fundraise", "when": "rating", "equals": "declined"}},
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
                "storage_type": "core_column",
                "is_required": f.get("is_required", False),
                "is_system": True,
                "display_order": f.get("display_order", 0),
                "section_name": f.get("section_name"),
                "validation_rules": f.get("validation_rules", {}),
                "dropdown_category": f.get("dropdown_category"),
                "dropdown_options": f.get("dropdown_options"),
                "default_value": f.get("default_value"),
                "is_active": True,
                "visibility_rules": f.get("visibility_rules", {}),
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

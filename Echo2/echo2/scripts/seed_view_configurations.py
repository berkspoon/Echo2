"""Seed view_configurations table with current hardcoded defaults.

Run:  cd echo2 && python -m scripts.seed_view_configurations [--force]

--force  overwrite existing rows (ON CONFLICT DO UPDATE)
default  skip existing rows (ON CONFLICT DO NOTHING via insert-if-missing)
"""

import argparse
import json
import sys

from db.client import get_supabase


# ---------------------------------------------------------------------------
# Seed rows — one dict per view_configuration record.
# Config values are extracted from current hardcoded sources.
# ---------------------------------------------------------------------------

SEED_ROWS = [
    # ── Distribution Lists ─────────────────────────────────────────────
    {
        "view_key": "dl_filter_fields",
        "display_name": "DL Filter Fields",
        "description": "Which person + org fields appear in the distribution list filter builder",
        "category": "distribution_lists",
        "config": {
            "person_fields": [],
            "org_fields": [
                {"field_name": "org_city", "display_name": "Org City", "field_type": "text", "dropdown_category": None},
                {"field_name": "org_country", "display_name": "Org Country", "field_type": "dropdown", "dropdown_category": "country"},
                {"field_name": "org_type", "display_name": "Org Type", "field_type": "dropdown", "dropdown_category": "organization_type"},
                {"field_name": "org_aum_mn", "display_name": "Org AUM ($M)", "field_type": "number", "dropdown_category": None},
            ],
            "include_field_types": [
                "text", "email", "phone", "url", "textarea",
                "dropdown", "multi_select", "number", "currency",
                "date", "boolean", "text_list",
            ],
        },
    },

    # ── Dashboard Tables ───────────────────────────────────────────────
    {
        "view_key": "cr_hot_prospects_columns",
        "display_name": "Hot Prospects Columns",
        "description": "Hot prospects table columns with conditional visibility",
        "category": "dashboards",
        "config": {
            "columns": [
                {"key": "org_name", "label": "Organization", "render_type": "link"},
                {"key": "stage_label", "label": "Stage", "render_type": "badge"},
                {"key": "owner_name", "label": "Lead Owner", "render_type": "text"},
                {"key": "allocation_fmt", "label": "Allocation ($M)", "render_type": "currency_right"},
            ],
        },
    },
    {
        "view_key": "cr_investor_breakdown_columns",
        "display_name": "Investor Breakdown Columns",
        "description": "Investor breakdown table columns",
        "category": "dashboards",
        "config": {
            "columns": [
                {"key": "label", "label": "LP Type", "render_type": "text"},
                {"key": "count", "label": "Count", "render_type": "text_right"},
                {"key": "target_fmt", "label": "Target ($M)", "render_type": "currency_right"},
                {"key": "soft_fmt", "label": "Soft Circle ($M)", "render_type": "currency_right"},
                {"key": "hard_fmt", "label": "Hard Circle ($M)", "render_type": "currency_right"},
            ],
        },
    },
    {
        "view_key": "cr_declined_columns",
        "display_name": "Declined Prospects Columns",
        "description": "Declined prospects table columns",
        "category": "dashboards",
        "config": {
            "columns": [
                {"key": "org_name", "label": "Organization", "render_type": "text"},
                {"key": "fund_ticker", "label": "Fund", "render_type": "mono"},
                {"key": "share_class", "label": "Share Class", "render_type": "text"},
                {"key": "decline_reason", "label": "Decline Reason", "render_type": "text"},
            ],
        },
    },

    # ── Dashboard Options ──────────────────────────────────────────────
    {
        "view_key": "cr_group_by_options",
        "display_name": "Capital Raise Group-By Options",
        "description": "Capital raise group-by dropdown options",
        "category": "dashboards",
        "config": {
            "options": [
                {"value": "stage", "label": "Stage"},
                {"value": "lp_type", "label": "LP Type"},
                {"value": "country", "label": "Country"},
                {"value": "fund", "label": "Fund"},
            ],
        },
    },
    {
        "view_key": "advisory_metric_options",
        "display_name": "Advisory Metric Options",
        "description": "Advisory pipeline metric selector options",
        "category": "dashboards",
        "config": {
            "options": [
                {"value": "count", "label": "Lead Count"},
                {"value": "revenue", "label": "Expected Revenue ($)"},
                {"value": "flar", "label": "Yr1 FLAR ($)"},
            ],
        },
    },

    # ── Grid Defaults ──────────────────────────────────────────────────
    {
        "view_key": "grid_defaults.organization",
        "display_name": "Organization Grid Defaults",
        "description": "Default visible columns for organization grid",
        "category": "grids",
        "config": {"columns": ["company_name", "relationship_type", "organization_type", "country", "aum_mn"]},
    },
    {
        "view_key": "grid_defaults.person",
        "display_name": "Person Grid Defaults",
        "description": "Default visible columns for person grid",
        "category": "grids",
        "config": {"columns": ["first_name", "last_name", "email", "phone", "job_title"]},
    },
    {
        "view_key": "grid_defaults.lead",
        "display_name": "Lead Grid Defaults",
        "description": "Default visible columns for lead grid",
        "category": "grids",
        "config": {"columns": ["organization_id", "lead_type", "rating", "service_type", "aksia_owner_id", "expected_revenue", "expected_yr1_flar", "start_date"]},
    },
    {
        "view_key": "grid_defaults.activity",
        "display_name": "Activity Grid Defaults",
        "description": "Default visible columns for activity grid",
        "category": "grids",
        "config": {"columns": ["effective_date", "title", "activity_type", "author_id"]},
    },
    {
        "view_key": "grid_defaults.contract",
        "display_name": "Contract Grid Defaults",
        "description": "Default visible columns for contract grid",
        "category": "grids",
        "config": {"columns": ["organization_id", "service_type", "asset_classes", "client_coverage", "actual_revenue", "start_date"]},
    },
    {
        "view_key": "grid_defaults.task",
        "display_name": "Task Grid Defaults",
        "description": "Default visible columns for task grid",
        "category": "grids",
        "config": {"columns": ["status", "title", "due_date", "assigned_to", "source", "linked_record_type"]},
    },
    {
        "view_key": "grid_defaults.distribution_list",
        "display_name": "Distribution List Grid Defaults",
        "description": "Default visible columns for distribution list grid",
        "category": "grids",
        "config": {"columns": ["list_name", "list_type", "list_mode", "brand", "asset_class", "frequency", "created_at"]},
    },
]


def main():
    parser = argparse.ArgumentParser(description="Seed view_configurations table")
    parser.add_argument("--force", action="store_true", help="Overwrite existing rows")
    args = parser.parse_args()

    sb = get_supabase()

    created = 0
    skipped = 0
    updated = 0

    for row in SEED_ROWS:
        view_key = row["view_key"]

        if args.force:
            # Upsert — overwrite config if row exists
            sb.table("view_configurations").upsert(
                row, on_conflict="view_key"
            ).execute()
            updated += 1
            print(f"  upserted: {view_key}")
        else:
            # Check if row already exists
            existing = (
                sb.table("view_configurations")
                .select("id")
                .eq("view_key", view_key)
                .maybe_single()
                .execute()
            )
            if existing and existing.data:
                skipped += 1
                print(f"  skipped (exists): {view_key}")
            else:
                sb.table("view_configurations").insert(row).execute()
                created += 1
                print(f"  created: {view_key}")

    print(f"\nDone. Created: {created}, Skipped: {skipped}, Updated: {updated}")


if __name__ == "__main__":
    main()

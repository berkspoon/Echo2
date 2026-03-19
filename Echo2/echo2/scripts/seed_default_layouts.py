"""Seed default page_layouts from current field_definitions section_name assignments.

feedback: [padelsbach] sections should only exist at layout level, not on field definitions.
This script reads the current field_definitions grouped by section_name and creates
default page_layouts entries so the form_service can use layouts as the authoritative
section grouping source.

Run: cd echo2 && python -m scripts.seed_default_layouts [--force]
"""

import sys

from db.client import get_supabase


ENTITY_TYPES = [
    "organization", "person", "lead", "activity",
    "contract", "task", "distribution_list",
]


def seed(force: bool = False):
    sb = get_supabase()

    for entity_type in ENTITY_TYPES:
        # Check if layout already exists
        existing = (
            sb.table("page_layouts")
            .select("id")
            .eq("entity_type", entity_type)
            .eq("layout_type", "edit")
            .eq("is_active", True)
            .execute()
        )
        if existing.data and not force:
            print(f"  {entity_type}: layout already exists, skipping (use --force to overwrite)")
            continue

        # Load field definitions grouped by section
        fd_resp = (
            sb.table("field_definitions")
            .select("field_name, section_name, display_order")
            .eq("entity_type", entity_type)
            .eq("is_active", True)
            .order("section_name")
            .order("display_order")
            .execute()
        )
        fields = fd_resp.data or []
        if not fields:
            print(f"  {entity_type}: no field definitions found, skipping")
            continue

        # Group by section_name, preserving order
        section_map: dict[str, list[str]] = {}
        for fd in fields:
            sec = fd.get("section_name") or "Other"
            section_map.setdefault(sec, []).append(fd["field_name"])

        sections_json = [
            {"name": sec_name, "fields": field_names}
            for sec_name, field_names in section_map.items()
        ]

        if existing.data and force:
            # Update existing layout
            sb.table("page_layouts").update({
                "sections": sections_json,
            }).eq("id", existing.data[0]["id"]).execute()
            print(f"  {entity_type}: updated layout ({len(sections_json)} sections)")
        else:
            # Insert new layout
            sb.table("page_layouts").insert({
                "entity_type": entity_type,
                "layout_type": "edit",
                "sections": sections_json,
                "is_active": True,
            }).execute()
            print(f"  {entity_type}: created layout ({len(sections_json)} sections)")


if __name__ == "__main__":
    force = "--force" in sys.argv
    print("Seeding default page layouts from field_definitions...")
    seed(force=force)
    print("Done.")

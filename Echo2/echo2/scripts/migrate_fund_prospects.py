"""Migrate fund_prospects rows → leads with lead_type='fundraise'.

Idempotent — safe to re-run. Checks for previously migrated rows before inserting.
Does NOT drop the fund_prospects table (kept as backup).

Usage:
    cd echo2
    python -m scripts.migrate_fund_prospects          # dry-run (default)
    python -m scripts.migrate_fund_prospects --apply   # actually write to DB
"""

import argparse
import sys
from uuid import UUID

from db.client import get_supabase

# ---------------------------------------------------------------------------
# Stage mapping: fund_prospect.stage → lead.rating (lead_stage with parent_value='fundraise')
# ---------------------------------------------------------------------------
FP_STAGE_TO_LEAD_RATING = {
    "target_identified": "target_identified",
    "intro_scheduled": "intro_scheduled",
    "initial_meeting_complete": "initial_meeting_complete",
    "ddq_materials_sent": "ddq_materials_sent",
    "due_diligence": "due_diligence",
    "ic_review": "ic_review",
    "soft_circle": "soft_circle",
    "legal_docs": "legal_docs",
    "closed": "closed",
    "declined": "declined",
}


def migrate(*, dry_run: bool = True) -> None:
    sb = get_supabase()

    # ------------------------------------------------------------------
    # 1. Load all non-archived fund_prospects
    # ------------------------------------------------------------------
    fp_resp = sb.table("fund_prospects").select("*").execute()
    fund_prospects = fp_resp.data or []
    print(f"Found {len(fund_prospects)} fund_prospect rows (including archived).")

    if not fund_prospects:
        print("Nothing to migrate.")
        return

    # ------------------------------------------------------------------
    # 2. Check for previously migrated leads (idempotency)
    #    We store the original fund_prospect id in the lead's summary field
    #    as a migration marker: "[migrated:fp:<uuid>]"
    # ------------------------------------------------------------------
    existing_leads_resp = (
        sb.table("leads")
        .select("summary")
        .eq("lead_type", "fundraise")
        .like("summary", "[migrated:fp:%")
        .execute()
    )
    already_migrated_fp_ids: set[str] = set()
    for lead in (existing_leads_resp.data or []):
        summary = lead.get("summary") or ""
        # Extract the FP id from "[migrated:fp:<uuid>] ..."
        if summary.startswith("[migrated:fp:"):
            fp_id = summary.split("]")[0].replace("[migrated:fp:", "")
            already_migrated_fp_ids.add(fp_id)

    skipped = 0
    migrated = 0
    errors = 0

    for fp in fund_prospects:
        fp_id = fp["id"]

        if fp_id in already_migrated_fp_ids:
            skipped += 1
            continue

        # Map fund_prospect fields → lead fields
        stage = fp.get("stage", "target_identified")
        lead_rating = FP_STAGE_TO_LEAD_RATING.get(stage, stage)

        # Build summary with migration marker
        notes = fp.get("notes") or ""
        summary_marker = f"[migrated:fp:{fp_id}]"
        summary = f"{summary_marker} {notes}".strip() if notes else summary_marker

        lead_data = {
            "organization_id": fp["organization_id"],
            "lead_type": "fundraise",
            "rating": lead_rating,
            "fund_id": fp.get("fund_id"),
            "share_class": fp.get("share_class"),
            "decline_reason": fp.get("decline_reason"),
            "aksia_owner_id": fp.get("aksia_owner_id"),
            "target_allocation_mn": fp.get("target_allocation_mn"),
            "soft_circle_mn": fp.get("soft_circle_mn"),
            "hard_circle_mn": fp.get("hard_circle_mn"),
            "probability_pct": fp.get("probability_pct"),
            "stage_entry_date": fp.get("stage_entry_date"),
            "next_steps": fp.get("next_steps"),
            "next_steps_date": fp.get("next_steps_date"),
            "summary": summary,
            "start_date": (fp.get("created_at") or "")[:10] or None,
            "is_deleted": fp.get("is_deleted", False),
            "created_by": fp.get("created_by"),
        }

        # Remove None values to let DB defaults apply
        lead_data = {k: v for k, v in lead_data.items() if v is not None}

        if dry_run:
            print(f"  [DRY-RUN] Would migrate FP {fp_id} → lead (stage={lead_rating})")
            migrated += 1
            continue

        try:
            # Insert lead
            result = sb.table("leads").insert(lead_data).execute()
            new_lead = result.data[0] if result.data else None

            if not new_lead:
                print(f"  [ERROR] Failed to insert lead for FP {fp_id}")
                errors += 1
                continue

            new_lead_id = new_lead["id"]

            # Create lead_owners row (matching the aksia_owner_id)
            owner_id = fp.get("aksia_owner_id")
            if owner_id:
                sb.table("lead_owners").insert({
                    "lead_id": new_lead_id,
                    "user_id": owner_id,
                    "is_primary": True,
                }).execute()

            # Update tasks: fund_prospect → lead
            sb.table("tasks").update({
                "linked_record_type": "lead",
                "linked_record_id": new_lead_id,
            }).eq("linked_record_type", "fund_prospect").eq(
                "linked_record_id", fp_id
            ).execute()

            # Update record_tags: fund_prospect → lead
            sb.table("record_tags").update({
                "record_type": "lead",
                "record_id": new_lead_id,
            }).eq("record_type", "fund_prospect").eq(
                "record_id", fp_id
            ).execute()

            # Update audit_log: fund_prospect → lead (for continuity)
            sb.table("audit_log").update({
                "record_type": "lead",
                "record_id": new_lead_id,
            }).eq("record_type", "fund_prospect").eq(
                "record_id", fp_id
            ).execute()

            migrated += 1
            print(f"  Migrated FP {fp_id} → Lead {new_lead_id}")

        except Exception as e:
            print(f"  [ERROR] FP {fp_id}: {e}")
            errors += 1

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    mode = "DRY-RUN" if dry_run else "APPLIED"
    print(f"\n{'='*60}")
    print(f"Migration complete ({mode})")
    print(f"  Total fund_prospects: {len(fund_prospects)}")
    print(f"  Already migrated (skipped): {skipped}")
    print(f"  Newly migrated: {migrated}")
    print(f"  Errors: {errors}")
    print(f"{'='*60}")

    if dry_run and migrated > 0:
        print("\nRe-run with --apply to execute the migration.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate fund_prospects to leads")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes (default is dry-run)",
    )
    args = parser.parse_args()
    migrate(dry_run=not args.apply)

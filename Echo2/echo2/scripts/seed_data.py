"""Dummy data generator for Echo 2.0 CRM.

Populates all tables with ~2,500 realistic rows for testing.
Uses Faker for realistic names/emails/dates and inserts directly into Supabase.

Usage:
    cd echo2
    python -m scripts.seed_data          # first run
    python -m scripts.seed_data --force  # re-seed (cleans existing seed data first)
"""

import argparse
import random
import sys
import os
from datetime import date, timedelta, datetime
from decimal import Decimal
from uuid import uuid4

from faker import Faker

# ---------------------------------------------------------------------------
# Setup: make sure we can import from the echo2 package
# ---------------------------------------------------------------------------
# When run as `python -m scripts.seed_data` from echo2/, the cwd is echo2/
# But just in case, add the parent of this file's directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.client import get_supabase

fake = Faker()
Faker.seed(42)
random.seed(42)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SEED_EMAIL_DOMAIN = "@aksia.test"
DEV_USER_ID = "00000000-0000-0000-0000-000000000001"

SEED_USERS = [
    {"email": "seed-admin@aksia.test", "display_name": "Miles Greenspoon", "first_name": "Miles", "last_name": "Greenspoon", "role": "admin", "entra_id": "seed-admin-entra-1"},
    {"email": "seed-legal@aksia.test", "display_name": "Sarah Mitchell", "first_name": "Sarah", "last_name": "Mitchell", "role": "legal", "entra_id": "seed-legal-entra-1"},
    {"email": "seed-rfp@aksia.test", "display_name": "Tom Nakamura", "first_name": "Tom", "last_name": "Nakamura", "role": "rfp_team", "entra_id": "seed-rfp-entra-1"},
    {"email": "seed-user1@aksia.test", "display_name": "Jessica Park", "first_name": "Jessica", "last_name": "Park", "role": "standard_user", "entra_id": "seed-user1-entra-1"},
    {"email": "seed-user2@aksia.test", "display_name": "David Chen", "first_name": "David", "last_name": "Chen", "role": "standard_user", "entra_id": "seed-user2-entra-1"},
    {"email": "seed-user3@aksia.test", "display_name": "Maria Rodriguez", "first_name": "Maria", "last_name": "Rodriguez", "role": "standard_user", "entra_id": "seed-user3-entra-1"},
    {"email": "seed-user4@aksia.test", "display_name": "James O'Brien", "first_name": "James", "last_name": "O'Brien", "role": "standard_user", "entra_id": "seed-user4-entra-1"},
    {"email": "seed-readonly@aksia.test", "display_name": "View Only", "first_name": "View", "last_name": "Only", "role": "read_only", "entra_id": "seed-readonly-entra-1"},
]

JOB_TITLES = [
    "Chief Investment Officer", "Portfolio Manager", "Director of Alternatives",
    "Managing Director", "Investment Analyst", "VP of Investments",
    "Head of Research", "Senior Portfolio Manager", "Investment Director",
    "Chief Financial Officer", "Treasurer", "Deputy CIO",
    "Head of Private Equity", "Head of Hedge Funds", "Head of Credit",
    "Investment Committee Member", "Board Member", "Executive Director",
    "Associate Director", "Senior Analyst", "Consultant",
    "Partner", "Principal", "Fund Manager",
]

FINANCIAL_CITIES = [
    ("New York", "NY", "US"), ("Boston", "MA", "US"), ("Chicago", "IL", "US"),
    ("San Francisco", "CA", "US"), ("Los Angeles", "CA", "US"), ("Houston", "TX", "US"),
    ("London", None, "GB"), ("Edinburgh", None, "GB"),
    ("Toronto", "ON", "CA"), ("Montreal", "QC", "CA"),
    ("Frankfurt", None, "DE"), ("Munich", None, "DE"),
    ("Paris", None, "FR"), ("Zurich", None, "CH"), ("Geneva", None, "CH"),
    ("Tokyo", None, "JP"), ("Singapore", None, "SG"), ("Hong Kong", None, "HK"),
    ("Sydney", None, "AU"), ("Melbourne", None, "AU"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _batch_insert(table_name: str, rows: list[dict], batch_size: int = 50) -> list[dict]:
    """Insert rows in batches, return all inserted records with their IDs."""
    sb = get_supabase()
    all_results = []
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        result = sb.table(table_name).insert(batch).execute()
        all_results.extend(result.data)
    return all_results


def _load_reference_data() -> dict[str, list[str]]:
    """Load all reference_data values, grouped by category."""
    sb = get_supabase()
    result = sb.table("reference_data").select("category, value").eq("is_active", True).execute()
    ref = {}
    for row in result.data:
        ref.setdefault(row["category"], []).append(row["value"])
    return ref


def _load_fund_ids() -> dict[str, str]:
    """Load fund ticker → UUID mapping."""
    sb = get_supabase()
    result = sb.table("funds").select("id, ticker").eq("is_active", True).execute()
    return {row["ticker"]: row["id"] for row in result.data}


def _random_date(start_days_ago: int, end_days_ago: int = 0) -> str:
    """Return a random date between start_days_ago and end_days_ago as ISO string."""
    start = date.today() - timedelta(days=start_days_ago)
    end = date.today() - timedelta(days=end_days_ago)
    delta = (end - start).days
    if delta <= 0:
        return end.isoformat()
    return (start + timedelta(days=random.randint(0, delta))).isoformat()


def _random_future_date(min_days: int = 1, max_days: int = 90) -> str:
    """Return a random future date as ISO string."""
    return (date.today() + timedelta(days=random.randint(min_days, max_days))).isoformat()


def _pct(percentage: int) -> bool:
    """Return True with given percentage probability."""
    return random.randint(1, 100) <= percentage


# ---------------------------------------------------------------------------
# Seeding functions
# ---------------------------------------------------------------------------

def seed_users() -> list[str]:
    """Seed 8 test users. Returns list of user UUIDs."""
    sb = get_supabase()
    print("  Seeding users...")

    # Check if dev user exists; insert if not
    dev_check = sb.table("users").select("id").eq("id", DEV_USER_ID).execute()
    if not dev_check.data:
        sb.table("users").insert({
            "id": DEV_USER_ID,
            "entra_id": "dev-entra-placeholder",
            "email": "dev@aksia.com",
            "display_name": "Dev User",
            "first_name": "Dev",
            "last_name": "User",
            "role": "admin",
            "is_active": True,
        }).execute()

    # Insert seed users
    results = _batch_insert("users", SEED_USERS)
    user_ids = [DEV_USER_ID] + [r["id"] for r in results]
    print(f"    -> {len(results)} seed users + dev user = {len(user_ids)} total")
    return user_ids


def seed_organizations(user_ids: list[str], ref: dict) -> list[dict]:
    """Seed ~200 organizations. Returns list of inserted records."""
    print("  Seeding organizations...")

    relationship_weights = [("client", 30), ("prospect", 50), ("other", 20)]
    org_types = ref.get("organization_type", ["pension_fund", "endowment", "family_office"])
    countries = ref.get("country", ["US", "GB"])

    used_names = set()
    rows = []
    for i in range(200):
        name = fake.company()
        # Ensure unique names
        while name in used_names:
            name = fake.company() + f" {fake.company_suffix()}"
        used_names.add(name)

        rel = random.choices(
            [w[0] for w in relationship_weights],
            weights=[w[1] for w in relationship_weights],
        )[0]

        city_info = random.choice(FINANCIAL_CITIES)

        row = {
            "company_name": name,
            "short_name": name.split()[0] if len(name.split()) > 1 else None,
            "relationship_type": rel,
            "organization_type": random.choice(org_types),
            "country": city_info[2],
            "city": city_info[0],
            "state_province": city_info[1],
            "website": f"https://www.{name.lower().replace(' ', '').replace(',', '')[:20]}.com" if _pct(60) else None,
            "aum_mn": float(round(random.uniform(50, 50000), 2)) if _pct(70) else None,
            "rfp_hold": _pct(5),
            "is_archived": _pct(1),
            "created_by": random.choice(user_ids),
        }
        rows.append(row)

    results = _batch_insert("organizations", rows)
    print(f"    -> {len(results)} organizations")
    return results


def seed_people(user_ids: list[str], ref: dict) -> list[dict]:
    """Seed ~500 people. Returns list of inserted records."""
    print("  Seeding people...")

    asset_classes = ref.get("asset_class", ["hf", "pe", "pc"])

    rows = []
    for i in range(500):
        first = fake.first_name()
        last = fake.last_name()
        row = {
            "first_name": first,
            "last_name": last,
            "email": f"{first.lower()}.{last.lower()}@{fake.domain_name()}" if _pct(90) else None,
            "phone": fake.phone_number()[:20] if _pct(60) else None,
            "job_title": random.choice(JOB_TITLES),
            "asset_classes_of_interest": random.sample(asset_classes, k=random.randint(1, min(4, len(asset_classes)))) if _pct(50) else None,
            "coverage_owner": random.choice(user_ids),
            "do_not_contact": _pct(3),
            "is_archived": _pct(1),
            "created_by": random.choice(user_ids),
        }
        rows.append(row)

    results = _batch_insert("people", rows)
    print(f"    -> {len(results)} people")
    return results


def seed_person_org_links(people: list[dict], orgs: list[dict]) -> list[dict]:
    """Link every person to at least one org (primary). ~20% get secondary, ~5% get former."""
    print("  Seeding person-organization links...")

    org_ids = [o["id"] for o in orgs]
    rows = []
    used_pairs = set()

    for person in people:
        pid = person["id"]
        # Primary org
        primary_org = random.choice(org_ids)
        rows.append({
            "person_id": pid,
            "organization_id": primary_org,
            "link_type": "primary",
            "job_title_at_org": person.get("job_title"),
        })
        used_pairs.add((pid, primary_org))

        # Secondary (~20%)
        if _pct(20):
            sec_org = random.choice(org_ids)
            if (pid, sec_org) not in used_pairs:
                rows.append({
                    "person_id": pid,
                    "organization_id": sec_org,
                    "link_type": "secondary",
                })
                used_pairs.add((pid, sec_org))

        # Former (~5%)
        if _pct(5):
            former_org = random.choice(org_ids)
            if (pid, former_org) not in used_pairs:
                rows.append({
                    "person_id": pid,
                    "organization_id": former_org,
                    "link_type": "former",
                })
                used_pairs.add((pid, former_org))

    results = _batch_insert("person_organization_links", rows)
    print(f"    -> {len(results)} person-org links")
    return results


def seed_activities(user_ids: list[str], orgs: list[dict], people: list[dict], fund_ids: dict, ref: dict) -> list[dict]:
    """Seed ~500 activities with org and people links."""
    print("  Seeding activities...")

    activity_types = ref.get("activity_type", ["call", "meeting", "email", "note"])
    subtypes = ref.get("activity_subtype", ["in_person", "video_call", "conference_call"])
    type_weights = {"call": 25, "meeting": 30, "email": 20, "note": 15, "conference": 5, "webinar": 5}
    available_types = [t for t in activity_types if t in type_weights]
    weights = [type_weights.get(t, 10) for t in available_types]

    org_ids = [o["id"] for o in orgs]
    person_ids = [p["id"] for p in people]
    fund_id_list = list(fund_ids.values())

    activity_rows = []
    for i in range(500):
        atype = random.choices(available_types, weights=weights)[0]
        follow_up = _pct(15)
        eff_date = _random_date(730)  # within last 2 years

        row = {
            "title": f"{atype.replace('_', ' ').title()} — {fake.catch_phrase()[:60]}",
            "effective_date": eff_date,
            "activity_type": atype,
            "subtype": random.choice(subtypes) if atype == "meeting" else None,
            "author_id": random.choice(user_ids),
            "details": fake.paragraph(nb_sentences=random.randint(2, 5)),
            "follow_up_required": follow_up,
            "follow_up_date": (date.fromisoformat(eff_date) + timedelta(days=random.randint(7, 28))).isoformat() if follow_up else None,
            "follow_up_notes": fake.sentence() if follow_up else None,
            "fund_tags": random.sample(fund_id_list, k=random.randint(1, min(2, len(fund_id_list)))) if _pct(20) else None,
            "is_archived": _pct(1),
            "created_by": random.choice(user_ids),
        }
        activity_rows.append(row)

    activities = _batch_insert("activities", activity_rows)

    # Activity-Org links
    print("  Seeding activity-organization links...")
    aol_rows = []
    aol_used = set()
    for act in activities:
        n_orgs = random.choices([1, 2, 3], weights=[60, 30, 10])[0]
        linked_orgs = random.sample(org_ids, k=min(n_orgs, len(org_ids)))
        for oid in linked_orgs:
            key = (act["id"], oid)
            if key not in aol_used:
                aol_rows.append({"activity_id": act["id"], "organization_id": oid})
                aol_used.add(key)

    _batch_insert("activity_organization_links", aol_rows)
    print(f"    -> {len(aol_rows)} activity-org links")

    # Activity-People links (~80% of activities)
    print("  Seeding activity-people links...")
    apl_rows = []
    apl_used = set()
    for act in activities:
        if _pct(80):
            n_people = random.choices([1, 2], weights=[60, 40])[0]
            linked_people = random.sample(person_ids, k=min(n_people, len(person_ids)))
            for pid in linked_people:
                key = (act["id"], pid)
                if key not in apl_used:
                    apl_rows.append({"activity_id": act["id"], "person_id": pid})
                    apl_used.add(key)

    _batch_insert("activity_people_links", apl_rows)
    print(f"    -> {len(apl_rows)} activity-people links")
    print(f"    -> {len(activities)} activities total")
    return activities


def seed_leads(user_ids: list[str], orgs: list[dict], ref: dict) -> tuple[list[dict], list[dict]]:
    """Seed ~200 leads. Won leads auto-create contracts. Returns (leads, contracts)."""
    print("  Seeding leads...")

    org_ids = [o["id"] for o in orgs]
    service_types = ref.get("service_type", ["advisory", "discretionary", "research"])
    asset_classes = ref.get("asset_class", ["hf", "pe", "pc"])
    relationships = ref.get("lead_relationship_type", ["new", "upsell", "cross_sell"])
    pricing_proposals = ref.get("pricing_proposal", ["formal", "informal", "no_proposal"])
    rfp_statuses = ref.get("rfp_status", ["expected", "in_progress", "submitted", "not_applicable"])
    risk_weights = ref.get("risk_weight", ["high", "medium", "low"])

    # Stage distribution: 30% exploratory, 25% radar, 20% focus, 10% verbal, 10% won, 5% lost
    stage_dist = [
        ("exploratory", 30), ("radar", 25), ("focus", 20),
        ("verbal_mandate", 10), ("won", 10),
        ("lost_dropped_out", 2), ("lost_selected_other", 2), ("lost_nobody_hired", 1),
    ]
    stages = [s[0] for s in stage_dist]
    stage_weights = [s[1] for s in stage_dist]

    STAGE_RANK = {"exploratory": 1, "radar": 2, "focus": 3, "verbal_mandate": 4, "won": 5,
                  "lost_dropped_out": 5, "lost_selected_other": 5, "lost_nobody_hired": 5}

    lead_rows = []
    for i in range(200):
        stage = random.choices(stages, weights=stage_weights)[0]
        rank = STAGE_RANK[stage]
        start = _random_date(540)  # within last 18 months
        owner = random.choice(user_ids)
        rel = random.choice(relationships)
        svc = random.choice(service_types) if rank >= 2 else None
        acs = random.sample(asset_classes, k=random.randint(1, min(3, len(asset_classes)))) if rank >= 2 else None

        row = {
            "organization_id": random.choice(org_ids),
            "start_date": start,
            "rating": stage,
            "relationship": rel,
            "aksia_owner_id": owner,
            "service_type": svc,
            "asset_classes": acs,
            "source": fake.sentence(nb_words=4)[:100] if rank >= 2 else None,
            "summary": fake.sentence(nb_words=8)[:200] if _pct(70) else None,
            "is_archived": _pct(1),
            "created_by": random.choice(user_ids),
        }

        # Focus+ fields
        if rank >= 3:
            row["pricing_proposal"] = random.choice(pricing_proposals)
            row["expected_decision_date"] = _random_future_date(30, 180)
            row["expected_revenue"] = float(round(random.uniform(50000, 5000000), 2))
            row["expected_yr1_flar"] = float(round(random.uniform(20000, 2000000), 2))
            row["expected_longterm_flar"] = float(round(random.uniform(30000, 3000000), 2))
            row["rfp_status"] = random.choice(rfp_statuses)
            row["risk_weight"] = random.choice(risk_weights)
            if rel in ("contract_extension", "re_up"):
                row["previous_flar"] = float(round(random.uniform(10000, 1500000), 2))

        # Verbal Mandate+ fields
        if rank >= 4:
            row["legacy_onboarding"] = _pct(30)
            row["potential_coverage"] = random.choice(user_ids)

        # Won leads: set end_date
        if stage == "won":
            row["end_date"] = date.today().isoformat()

        # Lost leads: set end_date
        if stage.startswith("lost_"):
            row["end_date"] = _random_date(180)

        # Next steps for active leads
        if stage in ("exploratory", "radar", "focus", "verbal_mandate") and _pct(30):
            row["next_steps"] = fake.sentence()
            row["next_steps_date"] = _random_future_date(7, 60)

        lead_rows.append(row)

    leads = _batch_insert("leads", lead_rows)
    print(f"    -> {len(leads)} leads")

    # Create contracts from won leads
    print("  Seeding contracts from won leads...")
    won_leads = [l for l in leads if l["rating"] == "won"]
    contract_rows = []
    for lead in won_leads:
        contract_rows.append({
            "organization_id": lead["organization_id"],
            "originating_lead_id": lead["id"],
            "start_date": lead.get("end_date", date.today().isoformat()),
            "service_type": lead.get("service_type") or "advisory",
            "asset_classes": lead.get("asset_classes") or ["hf"],
            "actual_revenue": lead.get("expected_revenue") or float(round(random.uniform(100000, 3000000), 2)),
            "client_coverage": lead.get("potential_coverage"),
            "created_by": random.choice(user_ids),
        })

    contracts = _batch_insert("contracts", contract_rows) if contract_rows else []
    print(f"    -> {len(contracts)} contracts (from {len(won_leads)} won leads)")
    return leads, contracts


def seed_fund_prospects(user_ids: list[str], orgs: list[dict], fund_ids: dict, leads: list[dict], ref: dict) -> list[dict]:
    """Seed ~150 fund prospects."""
    print("  Seeding fund prospects...")

    org_ids = [o["id"] for o in orgs]
    fund_tickers = list(fund_ids.keys())
    decline_reasons = ref.get("decline_reason", ["strategy_fit", "timing", "competitive"])

    # Stage distribution
    stage_dist = [
        ("target_identified", 15), ("intro_scheduled", 12), ("initial_meeting_complete", 12),
        ("ddq_materials_sent", 10), ("due_diligence", 12), ("ic_review", 10),
        ("soft_circle", 8), ("legal_docs", 6), ("closed", 10), ("declined", 5),
    ]
    fp_stages = [s[0] for s in stage_dist]
    fp_weights = [s[1] for s in stage_dist]

    # Probability by stage
    prob_ranges = {
        "target_identified": (5, 15), "intro_scheduled": (10, 25),
        "initial_meeting_complete": (15, 35), "ddq_materials_sent": (25, 45),
        "due_diligence": (35, 55), "ic_review": (45, 65),
        "soft_circle": (55, 80), "legal_docs": (70, 90),
        "closed": (100, 100), "declined": (0, 0),
    }

    # Build a list of lead IDs per org for linked_lead_id
    leads_by_org = {}
    for lead in leads:
        leads_by_org.setdefault(lead["organization_id"], []).append(lead["id"])

    rows = []
    for i in range(150):
        stage = random.choices(fp_stages, weights=fp_weights)[0]
        ticker = random.choice(fund_tickers)
        org_id = random.choice(org_ids)
        prob = prob_ranges.get(stage, (10, 50))

        row = {
            "organization_id": org_id,
            "fund_id": fund_ids[ticker],
            "share_class": "domestic" if _pct(60) else "offshore",
            "stage": stage,
            "aksia_owner_id": random.choice(user_ids),
            "target_allocation_mn": float(round(random.uniform(0.5, 50), 2)) if _pct(80) else None,
            "soft_circle_mn": float(round(random.uniform(0.5, 30), 2)) if stage in ("soft_circle", "legal_docs", "closed") else None,
            "hard_circle_mn": float(round(random.uniform(0.5, 25), 2)) if stage in ("legal_docs", "closed") else None,
            "probability_pct": random.randint(prob[0], prob[1]) if prob[1] > 0 else 0,
            "stage_entry_date": _random_date(365),
            "decline_reason": random.choice(decline_reasons) if stage == "declined" else None,
            "notes": fake.sentence() if _pct(40) else None,
            "is_archived": _pct(1),
            "created_by": random.choice(user_ids),
        }

        # Link to a lead for this org if one exists
        if org_id in leads_by_org and _pct(30):
            row["linked_lead_id"] = random.choice(leads_by_org[org_id])

        # Next steps for active prospects
        if stage not in ("closed", "declined") and _pct(25):
            row["next_steps"] = fake.sentence()
            row["next_steps_date"] = _random_future_date(7, 60)

        rows.append(row)

    results = _batch_insert("fund_prospects", rows)
    print(f"    -> {len(results)} fund prospects")
    return results


def seed_distribution_lists(user_ids: list[str], ref: dict) -> list[dict]:
    """Seed distribution lists: 17 official + ~10 custom."""
    print("  Seeding distribution lists...")

    # Official publication lists (L1 and L2 for HF, PE, PC, RA)
    official_rows = []
    asset_classes = ["hf", "pe", "pc", "ra"]
    ac_labels = {"hf": "HF", "pe": "PE", "pc": "PC", "ra": "RA"}

    for ac in asset_classes:
        label = ac_labels[ac]
        # L1
        official_rows.append({
            "list_name": f"{label} L1",
            "list_type": "publication",
            "brand": "aksia",
            "asset_class": ac,
            "is_official": True,
            "is_private": False,
            "owner_id": user_ids[0],
            "created_by": user_ids[0],
        })
        # L2
        official_rows.append({
            "list_name": f"{label} L2",
            "list_type": "publication",
            "brand": "aksia",
            "asset_class": ac,
            "is_official": True,
            "is_private": False,
            "owner_id": user_ids[0],
            "created_by": user_ids[0],
        })

    # Newsletter
    official_rows.append({
        "list_name": "Aksia Newsletter",
        "list_type": "newsletter",
        "brand": "aksia",
        "is_official": True,
        "is_private": False,
        "owner_id": user_ids[0],
        "created_by": user_ids[0],
    })

    # Fund lists
    fund_lists = [
        ("APC Fund Updates", "aksia", "APC"),
        ("CAPIX Fund Updates", "acpm", "CAPIX"),
        ("CAPVX Fund Updates", "acpm", "CAPVX"),
        ("HEDGX Fund Updates", "acpm", "HEDGX"),
        ("ACPM Combined", "acpm", "ACPM"),
    ]
    for name, brand, _ticker in fund_lists:
        official_rows.append({
            "list_name": name,
            "list_type": "fund",
            "brand": brand,
            "is_official": True,
            "is_private": False,
            "owner_id": user_ids[0],
            "created_by": user_ids[0],
        })

    official_results = _batch_insert("distribution_lists", official_rows)

    # Set L2 → L1 superset relationships
    sb = get_supabase()
    l1_map = {}  # asset_class -> L1 list ID
    for dl in official_results:
        if dl["list_type"] == "publication" and dl["list_name"].endswith("L1"):
            ac = dl["asset_class"]
            l1_map[ac] = dl["id"]

    for dl in official_results:
        if dl["list_type"] == "publication" and dl["list_name"].endswith("L2"):
            ac = dl["asset_class"]
            if ac in l1_map:
                sb.table("distribution_lists").update(
                    {"l2_superset_of": l1_map[ac]}
                ).eq("id", dl["id"]).execute()

    # Custom lists (~10)
    custom_rows = []
    custom_names = [
        "Q1 2026 Investor Outreach", "Annual Conference Attendees", "PE Co-Invest Interest",
        "APAC Prospects", "Credit Strategy Updates", "Board Meeting Invites",
        "Monthly Market Commentary", "New LP Onboarding", "Product Launch Contacts",
        "Holiday Event 2025",
    ]
    for name in custom_names:
        owner = random.choice(user_ids[1:])  # not admin
        custom_rows.append({
            "list_name": name,
            "list_type": random.choice(["custom", "event"]),
            "is_official": False,
            "is_private": _pct(50),
            "owner_id": owner,
            "created_by": owner,
        })

    custom_results = _batch_insert("distribution_lists", custom_rows)

    all_lists = official_results + custom_results
    print(f"    -> {len(official_results)} official + {len(custom_results)} custom = {len(all_lists)} lists")
    return all_lists


def seed_distribution_list_members(dist_lists: list[dict], people: list[dict], user_ids: list[str]) -> int:
    """Add people to distribution lists. Returns count of memberships."""
    print("  Seeding distribution list members...")

    # Filter out DNC people
    eligible_people = [p for p in people if not p.get("do_not_contact", False) and not p.get("is_archived", False)]
    eligible_ids = [p["id"] for p in eligible_people]

    if not eligible_ids:
        print("    -> 0 members (no eligible people)")
        return 0

    used_pairs = set()
    rows = []

    for dl in dist_lists:
        is_official = dl.get("is_official", False)
        n_members = random.randint(15, 40) if is_official else random.randint(5, 20)
        n_members = min(n_members, len(eligible_ids))
        members = random.sample(eligible_ids, k=n_members)

        for pid in members:
            key = (dl["id"], pid)
            if key not in used_pairs:
                rows.append({
                    "distribution_list_id": dl["id"],
                    "person_id": pid,
                    "is_active": True,
                    "coverage_owner_id": random.choice(user_ids) if _pct(50) else None,
                })
                used_pairs.add(key)

    results = _batch_insert("distribution_list_members", rows)
    print(f"    -> {len(results)} memberships")
    return len(results)


def seed_tasks(user_ids: list[str], activities: list[dict], leads: list[dict],
               fund_prospects: list[dict], orgs: list[dict], people: list[dict]) -> list[dict]:
    """Seed ~200 tasks: manual + system-generated types."""
    print("  Seeding tasks...")

    org_ids = [o["id"] for o in orgs]
    person_ids = [p["id"] for p in people]
    statuses = ["open", "in_progress", "complete", "cancelled"]
    status_weights = [50, 15, 25, 10]

    rows = []

    # Manual tasks (~100)
    manual_titles = [
        "Follow up with {}", "Schedule meeting with {}", "Send proposal to {}",
        "Review documents for {}", "Prepare presentation for {}", "Update CRM records for {}",
        "Draft email to {}", "Research background on {}", "Coordinate with team on {}",
        "Complete due diligence for {}",
    ]
    for i in range(100):
        title_template = random.choice(manual_titles)
        title = title_template.format(fake.company()[:30])
        status = random.choices(statuses, weights=status_weights)[0]
        assignee = random.choice(user_ids)

        # Determine due date: some overdue, some future, some today
        if _pct(15) and status in ("open", "in_progress"):
            # Overdue
            due = _random_date(60, 1)
        elif _pct(60):
            due = _random_future_date(1, 60)
        else:
            due = None

        # Optionally link to a record
        linked_type = None
        linked_id = None
        if _pct(40):
            link_choice = random.choice(["organization", "person", "lead", "fund_prospect"])
            linked_type = link_choice
            if link_choice == "organization":
                linked_id = random.choice(org_ids)
            elif link_choice == "person":
                linked_id = random.choice(person_ids)
            elif link_choice == "lead" and leads:
                linked_id = random.choice(leads)["id"]
            elif link_choice == "fund_prospect" and fund_prospects:
                linked_id = random.choice(fund_prospects)["id"]

        rows.append({
            "title": title,
            "due_date": due,
            "assigned_to": assignee,
            "status": status,
            "notes": fake.sentence() if _pct(40) else None,
            "source": "manual",
            "linked_record_type": linked_type,
            "linked_record_id": linked_id,
            "is_archived": _pct(1),
            "created_by": random.choice(user_ids),
        })

    # Activity follow-up tasks (~40)
    follow_up_activities = [a for a in activities if a.get("follow_up_required")][:40]
    for act in follow_up_activities:
        rows.append({
            "title": f"Follow up: {act.get('title', 'Activity')[:60]}",
            "due_date": act.get("follow_up_date"),
            "assigned_to": act["author_id"],
            "status": random.choices(["open", "in_progress", "complete"], weights=[50, 20, 30])[0],
            "notes": act.get("follow_up_notes"),
            "source": "activity_follow_up",
            "linked_record_type": "activity" if _pct(80) else None,
            "linked_record_id": act["id"] if _pct(80) else None,
            "created_by": act["author_id"],
        })

    # Lead next-steps tasks (~30)
    leads_with_ns = [l for l in leads if l.get("next_steps_date")][:30]
    for lead in leads_with_ns:
        rows.append({
            "title": f"Lead next step: {(lead.get('summary') or 'Lead follow-up')[:60]}",
            "due_date": lead["next_steps_date"],
            "assigned_to": lead.get("aksia_owner_id") or random.choice(user_ids),
            "status": random.choices(["open", "in_progress", "complete"], weights=[50, 20, 30])[0],
            "notes": lead.get("next_steps"),
            "source": "lead_next_steps",
            "linked_record_type": "lead",
            "linked_record_id": lead["id"],
            "created_by": lead.get("created_by") or random.choice(user_ids),
        })

    # Fund prospect next-steps tasks (~30)
    fps_with_ns = [fp for fp in fund_prospects if fp.get("next_steps_date")][:30]
    for fp in fps_with_ns:
        rows.append({
            "title": f"Fund prospect next step: {(fp.get('notes') or 'Follow up')[:50]}",
            "due_date": fp["next_steps_date"],
            "assigned_to": fp.get("aksia_owner_id") or random.choice(user_ids),
            "status": random.choices(["open", "in_progress", "complete"], weights=[50, 20, 30])[0],
            "notes": fp.get("next_steps"),
            "source": "fund_prospect_next_steps",
            "linked_record_type": "fund_prospect",
            "linked_record_id": fp["id"],
            "created_by": fp.get("created_by") or random.choice(user_ids),
        })

    results = _batch_insert("tasks", rows)
    print(f"    -> {len(results)} tasks (manual + follow-up + next-steps)")
    return results


def seed_fee_arrangements(user_ids: list[str], orgs: list[dict], ref: dict) -> list[dict]:
    """Seed ~50 fee arrangements for client organizations."""
    print("  Seeding fee arrangements...")

    client_orgs = [o for o in orgs if o.get("relationship_type") == "client" and not o.get("is_archived")]
    if not client_orgs:
        print("    -> 0 fee arrangements (no client orgs)")
        return []

    frequencies = ref.get("fee_frequency", ["monthly", "quarterly", "annual"])
    arrangement_names = [
        "Base Advisory Fee", "Performance Fee", "Research Retainer",
        "Discretionary Management Fee", "Consulting Fee", "Reporting Fee",
        "Project Fee", "Annual Retainer", "AUM-Based Fee",
    ]

    rows = []
    for i in range(50):
        org = random.choice(client_orgs)
        active = _pct(80)
        start = _random_date(730, 90)

        rows.append({
            "organization_id": org["id"],
            "arrangement_name": random.choice(arrangement_names),
            "annual_value": float(round(random.uniform(25000, 1000000), 2)),
            "frequency": random.choice(frequencies),
            "status": "active" if active else "inactive",
            "start_date": start,
            "end_date": _random_date(90) if not active else None,
            "notes": fake.sentence() if _pct(30) else None,
            "is_archived": _pct(1),
            "created_by": random.choice(user_ids),
        })

    results = _batch_insert("fee_arrangements", rows)
    print(f"    -> {len(results)} fee arrangements")
    return results


# ---------------------------------------------------------------------------
# Cleanup for --force mode
# ---------------------------------------------------------------------------

def cleanup_seed_data():
    """Remove all seed data inserted by this script."""
    sb = get_supabase()
    print("Cleaning up existing seed data...")

    # Get seed user IDs
    user_result = sb.table("users").select("id").ilike("email", f"%{SEED_EMAIL_DOMAIN}").execute()
    seed_user_ids = [u["id"] for u in user_result.data]

    if not seed_user_ids:
        print("  No seed users found, nothing to clean up.")
        return

    # Delete in reverse dependency order using hard deletes
    # (This is the ONE exception to soft-delete rule — we're cleaning test data)
    tables_to_clean = [
        "audit_log",
        "send_history",
        "distribution_list_members",
        "distribution_lists",
        "fee_arrangements",
        "tasks",
        "fund_prospects",
        "contracts",
        "leads",
        "activity_people_links",
        "activity_organization_links",
        "activities",
        "person_organization_links",
        "people",
        "organizations",
    ]

    for table in tables_to_clean:
        try:
            for uid in seed_user_ids:
                sb.table(table).delete().eq("created_by", uid).execute()
            # Also clean records created by dev user if they exist
            sb.table(table).delete().eq("created_by", DEV_USER_ID).execute()
        except Exception as e:
            print(f"  Warning: Could not clean {table}: {e}")

    # Delete seed users (but not the dev user)
    for uid in seed_user_ids:
        try:
            sb.table("users").delete().eq("id", uid).execute()
        except Exception as e:
            print(f"  Warning: Could not delete user {uid}: {e}")

    print("  Cleanup complete.")


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def seed_all():
    """Run all seeding functions in dependency order."""
    print("\n" + "=" * 60)
    print("Echo 2.0 — Dummy Data Generator")
    print("=" * 60 + "\n")

    # Load reference data and funds from DB
    print("Loading reference data and funds...")
    ref = _load_reference_data()
    fund_ids = _load_fund_ids()
    print(f"  -> {sum(len(v) for v in ref.values())} reference values across {len(ref)} categories")
    print(f"  -> {len(fund_ids)} funds: {', '.join(fund_ids.keys())}")
    print()

    # Seed in dependency order
    print("Inserting seed data...\n")

    user_ids = seed_users()
    orgs = seed_organizations(user_ids, ref)
    people = seed_people(user_ids, ref)
    seed_person_org_links(people, orgs)
    activities = seed_activities(user_ids, orgs, people, fund_ids, ref)
    leads, contracts = seed_leads(user_ids, orgs, ref)
    fund_prospects = seed_fund_prospects(user_ids, orgs, fund_ids, leads, ref)
    dist_lists = seed_distribution_lists(user_ids, ref)
    seed_distribution_list_members(dist_lists, people, user_ids)
    seed_tasks(user_ids, activities, leads, fund_prospects, orgs, people)
    seed_fee_arrangements(user_ids, orgs, ref)

    print("\n" + "=" * 60)
    print("Seeding complete!")
    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Echo 2.0 with dummy data (~2,500 rows)")
    parser.add_argument("--force", action="store_true", help="Re-seed even if data already exists (cleans up first)")
    args = parser.parse_args()

    # Check idempotency
    sb = get_supabase()
    existing = sb.table("users").select("id", count="exact").ilike("email", f"%{SEED_EMAIL_DOMAIN}").execute()

    if existing.data and len(existing.data) > 0 and not args.force:
        print(f"Seed data already exists ({len(existing.data)} seed users found).")
        print("Use --force to re-seed (will clean up existing seed data first).")
        sys.exit(0)

    if args.force and existing.data and len(existing.data) > 0:
        cleanup_seed_data()
        print()

    seed_all()

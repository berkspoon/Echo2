"""Import real CRM data from EchoData.xlsx into Echo 2.0.

Step 4 of the Echo 2.0 data import. Imports organizations, people,
leads, and contracts from the Power Apps CRM export.

Usage:
    cd echo2
    python -m scripts.import_echo_data              # dry-run (default)
    python -m scripts.import_echo_data --apply       # actually insert
"""

import argparse
import csv
import os
import sys
from datetime import datetime, date
from pathlib import Path

# ---------------------------------------------------------------------------
# Setup: ensure echo2 package is importable
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.client import get_supabase
from scripts.create_users import build_name_to_uuid_map, normalize_name, generate_entra_id

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent.parent  # Echo2/
ECHO_DATA_XLSX = _ROOT / "EchoData.xlsx"
ACTIVITIES_CSV = _ROOT / "cr932_crmactivities.csv"

# ---------------------------------------------------------------------------
# ID → Text Mapping Constants
# ---------------------------------------------------------------------------

ORG_ENTITY_TYPE_MAP = {
    1: "private_pension", 2: "financial_institution",
    3: "endowment_foundation", 4: "insurance_company",
    5: "sovereign_wealth_fund", 6: "public_pension",
    7: "other", 8: "government", 9: "supranational",
    10: "superannuation_fund", 11: "asset_manager_gp",
    12: "family_office", 13: "private_bank",
    14: "retail_platform", 15: "healthcare_organization",
    16: "wealth_manager_ria", 17: "conference_publication",
    19: "placement_agent",
    20: "private_pension_taft_hartley", 22: "consultant_ocio",
}

RELATIONSHIP_TYPE_MAP = {0: "prospect", 1: "client", 2: "other"}

COVERAGE_OFFICE_MAP = {1: "us", 2: "emea", 3: "tokyo", 4: "hk"}

SERVICE_TYPE_MAP = {
    1: "investment_management", 2: "advisory", 3: "research",
    4: "reporting", 5: "product", 6: "project", 7: "advisory_bps",
}

LEAD_STATUS_MAP = {
    1: "exploratory", 2: "radar", 3: "focus",
    4: "verbal_mandate", 5: "won", 10: "did_not_win",
}

ENGAGEMENT_STATUS_MAP = {
    1: "not_yet_contacted", 2: "prospect_contacted",
    3: "prospect_responded", 4: "initial_meeting",
    5: "ongoing_dialogue", 6: "pricing_proposal_submitted",
}

RELATIONSHIP_MAP = {
    1: "new_client",
    3: "existing_client_contract_extension",
    6: "existing_client_new_business",
}

RFP_STATUS_MAP = {
    1: "submitted", 2: "in_progress", 3: "expected", 4: "not_applicable",
}

RISK_WEIGHT_MAP = {0: "0_25", 1: "25_50", 2: "50_75", 3: "75_100"}

WAYSTONE_MAP = {1: "yes", 2: "no", 3: "not_applicable"}

COMMITMENT_STATUS_MAP = {
    1: "initial_review", 2: "in_diligence", 3: "ic_approved",
    4: "on_hold", 5: "legal_approved",
}

PRICING_PROPOSAL_MAP = {1: "formal", 2: "informal", 3: "no_proposal"}

ACTIVITY_TYPE_MAP = {1: "call", 2: "meeting", 3: "note", 4: "email"}

# Currency mapping — will be finalized after inspecting data
CURRENCY_MAP = {
    1: "usd", 2: "eur", 3: "gbp", 4: "jpy", 5: "aud",
    6: "chf", 7: "cad", 8: "hkd", 9: "sgd",
}

# ---------------------------------------------------------------------------
# Country Normalization
# ---------------------------------------------------------------------------

COUNTRY_MAP = {
    # United States
    "us": "US", "usa": "US", "united states": "US",
    "united states of america": "US", "untied states": "US",
    "u.s.": "US", "u.s.a.": "US", "america": "US",
    # United Kingdom
    "uk": "GB", "united kingdom": "GB", "england": "GB",
    "great britain": "GB", "gb": "GB", "scotland": "GB",
    "wales": "GB", "northern ireland": "GB",
    # UAE
    "uae": "AE", "united arab emirates": "AE", "dubai": "AE", "abu dhabi": "AE",
    # India
    "india": "IN", "mumbai": "IN",
    # China
    "china": "CN", "shanghai": "CN", "prc": "CN",
    # Japan
    "japan": "JP", "tokyo": "JP",
    # Germany
    "germany": "DE", "karlsruhe": "DE", "hannover": "DE",
    # France
    "france": "FR",
    # Switzerland
    "switzerland": "CH",
    # Canada
    "canada": "CA",
    # Australia
    "australia": "AU",
    # Singapore
    "singapore": "SG",
    # Hong Kong
    "hong kong": "HK",
    # Netherlands
    "netherlands": "NL", "the netherlands": "NL", "holland": "NL", "amsterdam": "NL",
    # South Korea
    "south korea": "KR", "korea": "KR", "republic of korea": "KR",
    # European countries
    "italy": "IT", "spain": "ES", "sweden": "SE", "norway": "NO",
    "denmark": "DK", "copenhagen": "DK", "finland": "FI",
    "ireland": "IE", "belgium": "BE", "austria": "AT", "luxembourg": "LU",
    "portugal": "PT", "greece": "GR", "poland": "PL",
    "czech republic": "CZ", "czechia": "CZ", "turkey": "TR",
    "russia": "RU", "liechtenstein": "LI", "monaco": "MC",
    # Middle East
    "israel": "IL", "saudi arabia": "SA", "ksa": "SA",
    "kuwait": "KW", "qatar": "QA", "bahrain": "BH", "oman": "OM",
    # Americas
    "brazil": "BR", "mexico": "MX", "chile": "CL",
    "colombia": "CO", "columbia": "CO", "peru": "PE",
    # Africa
    "south africa": "ZA", "nigeria": "NG", "kenya": "KE",
    # Asia-Pacific
    "taiwan": "TW", "malaysia": "MY", "thailand": "TH",
    "indonesia": "ID", "philippines": "PH", "new zealand": "NZ",
    # Offshore jurisdictions
    "bermuda": "BM", "cayman islands": "KY", "guernsey": "GG",
    "jersey": "JE", "isle of man": "IM", "puerto rico": "PR",
    # Additional countries found in data
    "armenia": "AM", "bahamas": "BS", "barbados": "BB", "brunei": "BN",
    "cyprus": "CY", "estonia": "EE", "georgia": "GE", "iceland": "IS",
    "jordan": "JO", "kazakhstan": "KZ", "lebanon": "LB", "lithuania": "LT",
    "panama": "PA", "slovenia": "SI",
    "people's republic of china": "CN", "principality of liechtenstein": "LI",
    "republic of azerbaijan": "AZ", "taipei city": "TW",
}

# New org types to upsert into reference_data
NEW_ORG_TYPES = [
    ("private_pension", "Private Pension", 15),
    ("financial_institution", "Financial Institution", 16),
    ("endowment_foundation", "Endowment / Foundation", 17),
    ("public_pension", "Public Pension", 18),
    ("supranational", "Supranational", 19),
    ("superannuation_fund", "Superannuation Fund", 20),
    ("asset_manager_gp", "Asset Manager / GP", 21),
    ("private_bank", "Private Bank", 22),
    ("retail_platform", "Retail Platform", 23),
    ("healthcare_organization", "Healthcare Organization", 24),
    ("wealth_manager_ria", "Wealth Manager / RIA", 25),
    ("conference_publication", "Conference / Publication", 26),
    ("private_pension_taft_hartley", "Private Pension (Taft-Hartley)", 27),
    ("consultant_ocio", "Consultant / OCIO", 28),
]

# Entity types that get power_apps_id EAV field
ENTITY_TYPES_WITH_PA_ID = ["organization", "person", "lead", "contract"]

# Tables to clean in reverse FK order
CLEANUP_TABLES = [
    "entity_custom_values",
    "audit_log",
    "send_history",
    "distribution_list_members",
    "distribution_lists",
    "fee_arrangements",
    "record_tags",
    "tasks",
    "documents",
    "fund_prospects",
    "lead_owners",
    "contracts",
    "leads",
    "activity_people_links",
    "activity_organization_links",
    "activity_lead_links",
    "activities",
    "person_coverage_owners",
    "person_organization_links",
    "people",
    "organizations",
]


# ---------------------------------------------------------------------------
# Safe value helpers
# ---------------------------------------------------------------------------

def safe_str(val) -> str | None:
    """Convert value to string, return None if empty/None."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def safe_numeric(val) -> float | None:
    """Convert value to float, return None if not numeric."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if val != val:  # NaN check
            return None
        return float(val)
    try:
        s = str(val).strip().replace(",", "")
        if not s:
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def safe_date(val) -> str | None:
    """Convert value to ISO date string. Handles datetime objects and strings."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, date):
        return val.isoformat()
    s = str(val).strip()
    if not s:
        return None
    # Strip fractional seconds (e.g. "2026-03-25 00:00:00.0000000")
    if "." in s:
        s = s.split(".")[0]
    # Try common date formats
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def safe_bool(val) -> bool:
    """Convert value to boolean. Treats 0/None/empty/false as False."""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    s = str(val).strip().lower()
    return s in ("true", "1", "yes", "y")


def safe_int(val) -> int | None:
    """Convert value to int, return None if not numeric."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if val != val:  # NaN
            return None
        return int(val)
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return None


def clean_uuid(val) -> str | None:
    """Clean a UUID string — strip braces, whitespace, lowercase."""
    if val is None:
        return None
    s = str(val).strip().strip("{}").lower()
    return s if s and len(s) >= 32 else None


def normalize_country(raw) -> str | None:
    """Normalize CRM country text to ISO-2 code."""
    if not raw or not isinstance(raw, str):
        return None
    key = raw.strip().lower()
    if not key:
        return None
    if key in COUNTRY_MAP:
        return COUNTRY_MAP[key]
    # Already ISO-2?
    if len(key) == 2 and key.isalpha():
        return key.upper()
    return None


def parse_asset_classes_txt(val) -> list[str]:
    """Parse comma-separated asset class text into list of lowercase values.
    E.g. 'HF, PE, PC' -> ['hf', 'pe', 'pc']
    """
    if not val or not isinstance(val, str):
        return []
    parts = [p.strip().lower().replace(" ", "_") for p in val.split(",")]
    return [p for p in parts if p]


def resolve_user(name_str, user_map: dict[str, str]) -> str | None:
    """Resolve a display name to a user UUID via the name map."""
    if not name_str or not isinstance(name_str, str):
        return None
    norm = normalize_name(name_str.strip())
    return user_map.get(norm)


def parse_lead_owners(owner_str, user_map: dict[str, str]) -> list[str]:
    """Parse semicolon-separated owner names into list of user UUIDs."""
    if not owner_str or not isinstance(owner_str, str):
        return []
    uuids = []
    seen = set()
    for name in owner_str.split(";"):
        name = name.strip().rstrip(",")
        if not name:
            continue
        uid = resolve_user(name, user_map)
        if uid and uid not in seen:
            uuids.append(uid)
            seen.add(uid)
    return uuids


# ---------------------------------------------------------------------------
# Batch insert helper
# ---------------------------------------------------------------------------

def _batch_insert(table_name: str, rows: list[dict], batch_size: int = 50) -> list[dict]:
    """Insert rows in batches, return all inserted records with their IDs."""
    sb = get_supabase()
    all_results: list[dict] = []
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        result = sb.table(table_name).insert(batch).execute()
        all_results.extend(result.data)
    return all_results


# ---------------------------------------------------------------------------
# Phase 0: Load Excel data
# ---------------------------------------------------------------------------

def load_excel_data(xlsx_path: Path) -> dict[str, list[dict]]:
    """Read all 4 entity sheets from EchoData.xlsx.

    Returns dict of {sheet_name: [row_dicts]}.
    Uses header-name-based access for robustness.
    """
    import openpyxl
    print("  Loading Excel data...")
    wb = openpyxl.load_workbook(str(xlsx_path), read_only=True, data_only=True)

    sheet_configs = {
        "Organizations":    {"header_row": 2, "data_start": 3},
        "People":           {"header_row": 2, "data_start": 3},
        "Leads":            {"header_row": 1, "data_start": 2},
        "Contracts":        {"header_row": 2, "data_start": 3},
        "ActivityEntities": {"header_row": 1, "data_start": 2},
    }

    result = {}
    for sheet_name, config in sheet_configs.items():
        ws = wb[sheet_name]
        rows_raw = list(ws.iter_rows(values_only=True))

        header_idx = config["header_row"] - 1
        if header_idx >= len(rows_raw):
            print(f"    WARNING: {sheet_name} has no header row at row {config['header_row']}")
            result[sheet_name] = []
            continue

        # Build headers — lowercase, strip, deduplicate
        raw_headers = rows_raw[header_idx]
        headers = []
        seen_headers = {}
        for i, h in enumerate(raw_headers):
            name = str(h).strip().lower() if h else f"_col_{i}"
            if name in seen_headers:
                seen_headers[name] += 1
                name = f"{name}_{seen_headers[name]}"
            else:
                seen_headers[name] = 0
            headers.append(name)

        # Parse data rows
        data = []
        for row in rows_raw[config["data_start"] - 1:]:
            row_dict = {}
            for i, val in enumerate(row):
                if i < len(headers):
                    row_dict[headers[i]] = val
            # Skip completely empty rows
            if any(v is not None for v in row_dict.values()):
                data.append(row_dict)

        result[sheet_name] = data
        print(f"    {sheet_name}: {len(data)} rows, {len(headers)} columns")

    wb.close()
    return result


# ---------------------------------------------------------------------------
# Phase 1: Ensure reference_data
# ---------------------------------------------------------------------------

def ensure_reference_data(*, dry_run: bool = True) -> None:
    """Upsert new organization_type values into reference_data."""
    sb = get_supabase()

    if dry_run:
        print(f"  [DRY-RUN] Would upsert {len(NEW_ORG_TYPES)} organization_type values")
        return

    for value, label, order in NEW_ORG_TYPES:
        sb.table("reference_data").upsert({
            "category": "organization_type",
            "value": value,
            "label": label,
            "display_order": order,
            "is_active": True,
        }, on_conflict="category,value").execute()

    print(f"  Upserted {len(NEW_ORG_TYPES)} organization_type values")


def ensure_country_reference_data(country_codes: set[str], *, dry_run: bool = True) -> None:
    """Upsert any new country codes into reference_data."""
    sb = get_supabase()

    # Get existing countries
    existing = sb.table("reference_data").select("value").eq("category", "country").execute()
    existing_codes = {r["value"] for r in existing.data}

    new_codes = country_codes - existing_codes
    if not new_codes:
        print("  No new country codes to add")
        return

    if dry_run:
        print(f"  [DRY-RUN] Would upsert {len(new_codes)} new country codes: {sorted(new_codes)}")
        return

    for i, code in enumerate(sorted(new_codes)):
        sb.table("reference_data").upsert({
            "category": "country",
            "value": code,
            "label": code,  # Will display as ISO-2; can be prettified later
            "display_order": 100 + i,
            "is_active": True,
        }, on_conflict="category,value").execute()

    print(f"  Upserted {len(new_codes)} new country codes: {sorted(new_codes)}")


# ---------------------------------------------------------------------------
# Phase 2: Ensure power_apps_id field_definitions
# ---------------------------------------------------------------------------

def ensure_power_apps_field_defs(*, dry_run: bool = True) -> dict[str, str]:
    """Create power_apps_id field_definition for each entity type.

    Returns: {entity_type: field_definition_id}
    """
    sb = get_supabase()
    result = {}

    for et in ENTITY_TYPES_WITH_PA_ID:
        existing = (
            sb.table("field_definitions")
            .select("id")
            .eq("entity_type", et)
            .eq("field_name", "power_apps_id")
            .execute()
        )
        if existing.data:
            result[et] = existing.data[0]["id"]
            print(f"  power_apps_id for {et}: exists ({existing.data[0]['id'][:8]}...)")
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would create power_apps_id field_definition for {et}")
            result[et] = "dry-run-placeholder"
            continue

        row = {
            "entity_type": et,
            "field_name": "power_apps_id",
            "display_name": "Power Apps ID",
            "field_type": "text",
            "storage_type": "eav",
            "is_required": False,
            "is_system": True,
            "display_order": 99,
            "section_name": "Legacy IDs",
            "is_active": True,
            "grid_default_visible": False,
        }
        resp = sb.table("field_definitions").insert(row).execute()
        fd_id = resp.data[0]["id"]
        result[et] = fd_id
        print(f"  Created power_apps_id for {et}: {fd_id[:8]}...")

    return result


# ---------------------------------------------------------------------------
# Phase 3: Cleanup existing entity data
# ---------------------------------------------------------------------------

def cleanup_entity_data(*, dry_run: bool = True) -> None:
    """Hard-delete all existing entity data. One-time import cleanup."""
    sb = get_supabase()

    if dry_run:
        print("  [DRY-RUN] Would delete all existing entity data:")
        for table in CLEANUP_TABLES:
            try:
                resp = sb.table(table).select("id", count="exact").execute()
                count = resp.count if resp.count is not None else len(resp.data)
                if count > 0:
                    print(f"    {table}: {count} rows")
            except Exception:
                pass
        return

    print("  Deleting all existing entity data...")
    for table in CLEANUP_TABLES:
        try:
            # Delete all rows — use a filter that matches everything
            # Supabase requires a filter, so we use neq on a non-existent value
            sb.table(table).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            print(f"    {table}: deleted")
        except Exception as e:
            print(f"    {table}: skipped ({e})")

    print("  Cleanup complete.")


# ---------------------------------------------------------------------------
# Phase 4: Import Organizations
# ---------------------------------------------------------------------------

def import_organizations(
    rows: list[dict],
    user_map: dict[str, str],
    *,
    dry_run: bool = True,
) -> dict[str, str]:
    """Import organizations from Excel data.

    Returns: {pa_org_uuid: echo_org_uuid} mapping for FK resolution.
    """
    pa_org_map: dict[str, str] = {}
    org_rows: list[dict] = []
    pa_uuids: list[str] = []
    skipped = 0
    country_warnings: list[str] = []
    all_countries: set[str] = set()

    for row in rows:
        pa_uuid = clean_uuid(row.get("organizationid"))
        name = safe_str(row.get("organizationname"))

        if not pa_uuid or not name:
            skipped += 1
            continue

        # ID→text mappings
        entity_type_id = safe_int(row.get("entitytype"))
        org_type = ORG_ENTITY_TYPE_MAP.get(entity_type_id, "other") if entity_type_id is not None else "other"

        rel_type_id = safe_int(row.get("relationshiptype"))
        rel_type = RELATIONSHIP_TYPE_MAP.get(rel_type_id, "other") if rel_type_id is not None else "other"

        cov_office_id = safe_int(row.get("coverageoffice"))
        # coverage_office stored as EAV or not on org — skip for now (Step 6)

        # Country normalization
        raw_country = safe_str(row.get("country"))
        country = normalize_country(raw_country)
        if raw_country and not country:
            country_warnings.append(raw_country)
        if country:
            all_countries.add(country)

        # Questionnaire author
        quest_author = safe_str(row.get("clientquestionaireauthor"))
        quest_user_id = resolve_user(quest_author, user_map) if quest_author else None

        # Ostrako ID — pick non-null from two possible columns
        ostrako = safe_str(row.get("ostrakoid")) or safe_str(row.get("ostrakoidnum"))

        # Backstop company ID
        orgid_val = row.get("orgid")
        backstop_id = str(int(orgid_val)) if safe_numeric(orgid_val) is not None else None

        org_row = {
            "company_name": name,
            "short_name": safe_str(row.get("shortname")),
            "organization_type": org_type,
            "relationship_type": rel_type,
            "aum_mn": safe_numeric(row.get("aummncurrency_base")),
            "aum_as_of_date": safe_date(row.get("aumasofdate")),
            "aum_source": safe_str(row.get("aumsource")),
            "website": safe_str(row.get("website")),
            "street_address": safe_str(row.get("address")),
            "country": country,
            "city": safe_str(row.get("city")),
            "state_province": safe_str(row.get("state")),
            "postal_code": safe_str(row.get("zipcode")),
            "rfp_hold": safe_bool(row.get("rfphold")),
            "target_allocation_source": safe_str(row.get("targetallocationsource")),
            "team_distribution_email": safe_str(row.get("teamdistributionlist")),
            "hf_target_allocation_pct": min(safe_numeric(row.get("hedgefundtargetallocationoftotalaum")) or 0, 100) or None,
            "pc_target_allocation_pct": min(safe_numeric(row.get("privatecredittargetallocationoftotalaum")) or 0, 100) or None,
            "pe_target_allocation_pct": min(safe_numeric(row.get("privateequitytargetallocationoftotalaum")) or 0, 100) or None,
            "ra_target_allocation_pct": min(safe_numeric(row.get("realassetstargetallocationoftotalaum")) or 0, 100) or None,
            "re_target_allocation_pct": min(safe_numeric(row.get("realestatetargetallocationoftotalaum")) or 0, 100) or None,
            "client_discloses_info": safe_bool(row.get("clientquestionnairetoggle")),
            "overall_aum_mn": safe_numeric(row.get("overallclientaum")),
            "questionnaire_filled_by": quest_user_id,
            "questionnaire_date": safe_date(row.get("aksiallc_clientquestionnairecompletedon")),
            "ostrako_id": ostrako,
            "backstop_company_id": backstop_id,
            "is_deleted": False,
        }

        org_rows.append(org_row)
        pa_uuids.append(pa_uuid)

    if dry_run:
        unique_countries = set(c for c in country_warnings)
        print(f"  [DRY-RUN] Would import {len(org_rows)} organizations (skipped {skipped})")
        if country_warnings:
            print(f"    Unmapped countries ({len(unique_countries)} unique): {sorted(unique_countries)[:20]}")
        print(f"    Country codes found: {len(all_countries)} unique")
        return {}

    # Insert orgs
    print(f"  Inserting {len(org_rows)} organizations...")
    results = _batch_insert("organizations", org_rows)

    # Build PA→Echo map
    for i, result in enumerate(results):
        pa_org_map[pa_uuids[i]] = result["id"]

    print(f"  -> {len(results)} organizations imported (skipped {skipped})")
    if country_warnings:
        unique_warnings = set(country_warnings)
        print(f"    Unmapped countries: {sorted(unique_warnings)[:10]}")

    return pa_org_map


# ---------------------------------------------------------------------------
# Phase 5: Import People + person_organization_links
# ---------------------------------------------------------------------------

def import_people(
    rows: list[dict],
    pa_org_map: dict[str, str],
    *,
    dry_run: bool = True,
) -> dict[str, str]:
    """Import people and create person_organization_links.

    Returns: {pa_person_uuid: echo_person_uuid} mapping.
    """
    pa_person_map: dict[str, str] = {}
    person_rows: list[dict] = []
    pa_uuids: list[str] = []
    org_link_data: list[tuple[int, str, str | None]] = []  # (person_row_idx, pa_org_uuid, job_title)
    skipped = 0
    no_org_link = 0

    for row in rows:
        pa_uuid = clean_uuid(row.get("peopleid"))
        first = safe_str(row.get("firstname")) or "Unknown"
        last = safe_str(row.get("lastname")) or "Unknown"

        if not pa_uuid:
            skipped += 1
            continue

        if first == "Unknown" and last == "Unknown":
            # Both names empty — check if there's any useful data
            if not safe_str(row.get("email")):
                skipped += 1
                continue

        person_row = {
            "first_name": first,
            "last_name": last,
            "email": safe_str(row.get("email")),
            "phone": safe_str(row.get("phone")),
            "job_title": safe_str(row.get("title")),
            "do_not_contact": safe_bool(row.get("donotcontact")),
            "legal_compliance_notices": safe_bool(row.get("legalcompliancenotices")),
            "is_deleted": False,
        }

        idx = len(person_rows)
        person_rows.append(person_row)
        pa_uuids.append(pa_uuid)

        # Org link data
        pa_org_uuid = clean_uuid(row.get("orgid"))
        job_title = safe_str(row.get("title"))
        if pa_org_uuid:
            org_link_data.append((idx, pa_org_uuid, job_title))
        else:
            no_org_link += 1

    if dry_run:
        linkable = sum(1 for _, org_uuid, _ in org_link_data if org_uuid in pa_org_map) if pa_org_map else len(org_link_data)
        print(f"  [DRY-RUN] Would import {len(person_rows)} people (skipped {skipped})")
        print(f"    Org links: {len(org_link_data)} with orgid, {no_org_link} without")
        return {}

    # Insert people
    print(f"  Inserting {len(person_rows)} people...")
    results = _batch_insert("people", person_rows)

    for i, result in enumerate(results):
        pa_person_map[pa_uuids[i]] = result["id"]

    # Create person_organization_links
    link_rows = []
    link_skipped = 0
    for idx, pa_org_uuid, job_title in org_link_data:
        echo_org_id = pa_org_map.get(pa_org_uuid)
        if not echo_org_id:
            link_skipped += 1
            continue
        echo_person_id = results[idx]["id"]
        link_rows.append({
            "person_id": echo_person_id,
            "organization_id": echo_org_id,
            "link_type": "primary",
            "job_title_at_org": job_title,
        })

    if link_rows:
        print(f"  Creating {len(link_rows)} person_organization_links...")
        _batch_insert("person_organization_links", link_rows)

    print(f"  -> {len(results)} people imported (skipped {skipped})")
    print(f"    {len(link_rows)} org links created ({link_skipped} org not found, {no_org_link} no orgid)")

    return pa_person_map


# ---------------------------------------------------------------------------
# Phase 6: Import Leads + lead_owners
# ---------------------------------------------------------------------------

def import_leads(
    rows: list[dict],
    pa_org_map: dict[str, str],
    user_map: dict[str, str],
    *,
    dry_run: bool = True,
) -> dict[str, str]:
    """Import leads and create lead_owners junction entries.

    Returns: {pa_lead_uuid: echo_lead_uuid} mapping.
    """
    pa_lead_map: dict[str, str] = {}
    lead_rows: list[dict] = []
    pa_uuids: list[str] = []
    owner_data: list[tuple[int, list[str]]] = []  # (lead_row_idx, [user_uuids])
    skipped = 0
    skipped_no_org = 0
    no_owner = 0
    currency_values: set = set()

    for row in rows:
        pa_uuid = clean_uuid(row.get("leadsid"))
        if not pa_uuid:
            skipped += 1
            continue

        # Resolve organization
        pa_org_uuid = clean_uuid(row.get("organizationlinked"))
        if dry_run:
            echo_org_id = "dry-run-placeholder" if pa_org_uuid else None
        else:
            echo_org_id = pa_org_map.get(pa_org_uuid) if pa_org_uuid else None
        if not echo_org_id:
            skipped_no_org += 1
            continue

        # ID→text mappings
        service_type_id = safe_int(row.get("servicetype"))
        service_type = SERVICE_TYPE_MAP.get(service_type_id) if service_type_id is not None else None
        lead_type = "product" if service_type_id == 5 else "service"

        rating_id = safe_int(row.get("leadstatus"))
        rating = LEAD_STATUS_MAP.get(rating_id, "exploratory") if rating_id is not None else "exploratory"

        engagement_id = safe_int(row.get("engagementstatus"))
        engagement = ENGAGEMENT_STATUS_MAP.get(engagement_id) if engagement_id is not None else None

        rel_id = safe_int(row.get("relationship"))
        relationship = RELATIONSHIP_MAP.get(rel_id) if rel_id is not None else None

        rfp_id = safe_int(row.get("rfpstatus"))
        rfp_status = RFP_STATUS_MAP.get(rfp_id) if rfp_id is not None else None

        risk_id = safe_int(row.get("riskweight"))
        risk_weight = RISK_WEIGHT_MAP.get(risk_id) if risk_id is not None else None

        waystone_id = safe_int(row.get("waystoneapproved"))
        waystone = WAYSTONE_MAP.get(waystone_id) if waystone_id is not None else None

        commit_id = safe_int(row.get("internalclientstatusinitialreview"))
        commitment = COMMITMENT_STATUS_MAP.get(commit_id) if commit_id is not None else None

        pricing_id = safe_int(row.get("typeofpricingproposal"))
        pricing = PRICING_PROPOSAL_MAP.get(pricing_id) if pricing_id is not None else None

        cov_office_id = safe_int(row.get("aksiallc_coverageoffice"))
        cov_office = COVERAGE_OFFICE_MAP.get(cov_office_id) if cov_office_id is not None else None

        currency_id = safe_int(row.get("aksiallc_currency"))
        currency = CURRENCY_MAP.get(currency_id) if currency_id is not None else None
        if currency_id is not None:
            currency_values.add(currency_id)

        # Owners
        owner_str = safe_str(row.get("owner"))
        owner_uuids = parse_lead_owners(owner_str, user_map)
        primary_owner = owner_uuids[0] if owner_uuids else None
        if not owner_uuids:
            no_owner += 1

        # is_deleted from currentstatus or isdeleted
        current_status = safe_str(row.get("currentstatus"))
        is_deleted = safe_bool(row.get("isdeleted"))
        if current_status and current_status.lower() != "active":
            is_deleted = True

        lead_row = {
            "organization_id": echo_org_id,
            "title": safe_str(row.get("aksiallc_leadname")),
            "lead_type": lead_type,
            "rating": rating,
            "service_type": service_type,
            "engagement_status": engagement,
            "asset_classes": parse_asset_classes_txt(safe_str(row.get("assetclasstxt"))),
            "relationship": relationship,
            "rfp_status": rfp_status,
            "risk_weight": risk_weight,
            "aksia_owner_id": primary_owner,
            "source": safe_str(row.get("leadsource")),
            "summary": safe_str(row.get("summary")),
            "pricing_proposal": pricing,
            "pricing_proposal_details": safe_str(row.get("pricingproposaldetails")),
            "expected_decision_date": safe_date(row.get("expecteddecisiondate")),
            "expected_fee": safe_numeric(row.get("expectedrevenueinclperffees_base")),
            "expected_revenue_notes": safe_str(row.get("expectedrevenuenotes")),
            "expected_yr1_flar": safe_numeric(row.get("expectedyear1flar_base")),
            "expected_longterm_flar": safe_numeric(row.get("expectedlongtermflar_base")),
            "rfp_expected_date": safe_date(row.get("expectedrfpdate")),
            "next_steps": safe_str(row.get("nextsteps")),
            "next_steps_date": safe_date(row.get("nextstepsdate")),
            "start_date": safe_date(row.get("createddate")) or date.today().isoformat(),
            "end_date": safe_date(row.get("leadenddate")),
            "legacy_onboarding": safe_bool(row.get("legacyonboarding")),
            "legacy_onboarding_holdings": safe_str(row.get("legacyonboardingholdings")),
            "decline_rationale": safe_str(row.get("declinerationale")),
            "decline_reason": safe_str(row.get("whydeclined")),
            "waystone_approved": waystone,
            "commitment_status": commitment,
            "prospect_contacted_date": safe_date(row.get("prospectcontacteddate")),
            "prospect_responded_date": safe_date(row.get("prospectrespondeddate")),
            "initial_meeting_date": safe_date(row.get("initialmeetingdate")),
            "initial_meeting_complete_date": safe_date(row.get("initialmeetingcompleted")),
            "indicative_size_high": safe_numeric(row.get("indicativesizehigh")),
            "indicative_size_low": safe_numeric(row.get("indicativesizelow")),
            "revenue_currency": currency,
            "expected_management_fee": safe_numeric(row.get("aksiallc_managementfee")),
            "expected_incentive_fee": safe_numeric(row.get("aksiallc_incentivefee")),
            "expected_preferred_return": safe_numeric(row.get("aksiallc_preferredreturn")),
            "coverage_office": cov_office,
            "gp_commitment": safe_str(row.get("aksiallc_gpcommitment")),
            "deployment_period": safe_str(row.get("aksiallc_deploymentperiod")),
            "expected_contract_start_date": safe_date(row.get("aksiallc_expectedcontractstartdate")),
            "is_deleted": is_deleted,
        }

        idx = len(lead_rows)
        lead_rows.append(lead_row)
        pa_uuids.append(pa_uuid)
        if owner_uuids:
            owner_data.append((idx, owner_uuids))

    if currency_values:
        print(f"  Currency ID values found: {sorted(currency_values)}")

    if dry_run:
        print(f"  [DRY-RUN] Would import {len(lead_rows)} leads (skipped {skipped}, no org {skipped_no_org})")
        print(f"    Owners: {len(owner_data)} leads with owners, {no_owner} without")
        return {}

    # Insert leads
    print(f"  Inserting {len(lead_rows)} leads...")
    results = _batch_insert("leads", lead_rows)

    for i, result in enumerate(results):
        pa_lead_map[pa_uuids[i]] = result["id"]

    # Create lead_owners
    lo_rows = []
    for idx, uuids in owner_data:
        echo_lead_id = results[idx]["id"]
        for j, uid in enumerate(uuids):
            lo_rows.append({
                "lead_id": echo_lead_id,
                "user_id": uid,
                "is_primary": j == 0,
            })

    if lo_rows:
        print(f"  Creating {len(lo_rows)} lead_owners entries...")
        _batch_insert("lead_owners", lo_rows)

    print(f"  -> {len(results)} leads imported (skipped {skipped}, no org {skipped_no_org})")
    print(f"    {len(lo_rows)} lead_owners created, {no_owner} leads without owner")

    return pa_lead_map


# ---------------------------------------------------------------------------
# Phase 7: Import Contracts
# ---------------------------------------------------------------------------

def import_contracts(
    rows: list[dict],
    pa_org_map: dict[str, str],
    pa_lead_map: dict[str, str],
    *,
    dry_run: bool = True,
) -> int:
    """Import contracts. Creates placeholder leads for orphans.

    Returns: count of imported contracts.
    """
    contract_rows: list[dict] = []
    pa_uuids: list[str] = []
    skipped = 0
    skipped_no_org = 0
    placeholder_leads = 0

    for row in rows:
        pa_uuid = clean_uuid(row.get("contractsid"))
        if not pa_uuid:
            skipped += 1
            continue

        # Resolve organization
        pa_org_uuid = clean_uuid(row.get("organizationlinked"))
        if dry_run:
            echo_org_id = "dry-run-placeholder" if pa_org_uuid else None
        else:
            echo_org_id = pa_org_map.get(pa_org_uuid) if pa_org_uuid else None
        if not echo_org_id:
            skipped_no_org += 1
            continue

        # Resolve originating lead
        pa_lead_uuid = clean_uuid(row.get("leadlinked"))
        if dry_run:
            echo_lead_id = "dry-run-placeholder" if pa_lead_uuid else None
        else:
            echo_lead_id = pa_lead_map.get(pa_lead_uuid) if pa_lead_uuid else None

        # Service type
        svc_id = safe_int(row.get("contractservicetype"))
        service_type = SERVICE_TYPE_MAP.get(svc_id, "advisory") if svc_id is not None else "advisory"

        # Asset classes
        asset_classes = parse_asset_classes_txt(safe_str(row.get("assetclasstxt")))

        # Summary + notes
        summary = safe_str(row.get("contractsummary")) or ""
        notes = safe_str(row.get("contractnotes"))
        if notes:
            summary = f"{summary}\n\n{notes}".strip() if summary else notes

        # is_deleted from currentstatus
        current_status = safe_str(row.get("currentstatus"))
        is_deleted = current_status and current_status.lower() != "active"

        # Create placeholder lead if needed (originating_lead_id is NOT NULL)
        if not echo_lead_id and not dry_run:
            sb = get_supabase()
            placeholder = sb.table("leads").insert({
                "organization_id": echo_org_id,
                "title": "[Imported] Contract placeholder",
                "lead_type": "service",
                "rating": "won",
                "start_date": safe_date(row.get("startdate")) or date.today().isoformat(),
                "is_deleted": False,
            }).execute()
            echo_lead_id = placeholder.data[0]["id"]
            placeholder_leads += 1

        if not echo_lead_id and dry_run:
            placeholder_leads += 1
            echo_lead_id = "placeholder"

        contract_row = {
            "organization_id": echo_org_id,
            "originating_lead_id": echo_lead_id,
            "start_date": safe_date(row.get("startdate")) or date.today().isoformat(),
            "service_type": service_type,
            "asset_classes": asset_classes or [],
            "summary": summary or None,
            "actual_revenue": safe_numeric(row.get("actualrevenue")) or 0.0,
            "client_coverage": safe_str(row.get("clientcoverage")),
            "inflation_provision": safe_str(row.get("inflationprovision")),
            "escalator_clause": safe_str(row.get("escalatorclause")),
            "is_deleted": bool(is_deleted),
        }

        contract_rows.append(contract_row)
        pa_uuids.append(pa_uuid)

    if dry_run:
        print(f"  [DRY-RUN] Would import {len(contract_rows)} contracts (skipped {skipped}, no org {skipped_no_org})")
        print(f"    {placeholder_leads} would need placeholder leads")
        return 0

    # Insert contracts
    print(f"  Inserting {len(contract_rows)} contracts...")
    results = _batch_insert("contracts", contract_rows)

    print(f"  -> {len(results)} contracts imported (skipped {skipped}, no org {skipped_no_org})")
    print(f"    {placeholder_leads} placeholder leads created")

    return len(results)


# ---------------------------------------------------------------------------
# Phase 8: Store EAV power_apps_id values
# ---------------------------------------------------------------------------

def store_eav_power_apps_ids(
    entity_type: str,
    pa_to_echo_map: dict[str, str],
    field_def_id: str,
    *,
    dry_run: bool = True,
) -> int:
    """Batch insert EAV power_apps_id values for an entity type."""
    rows = []
    for pa_uuid, echo_uuid in pa_to_echo_map.items():
        rows.append({
            "entity_type": entity_type,
            "entity_id": echo_uuid,
            "field_definition_id": field_def_id,
            "value_text": str(pa_uuid),
        })

    if dry_run:
        return len(rows)

    if rows:
        _batch_insert("entity_custom_values", rows, batch_size=50)
    return len(rows)


# ---------------------------------------------------------------------------
# Phase 9: Import Activities from CSV
# ---------------------------------------------------------------------------

def ensure_legacy_author(user_map: dict[str, str], *, dry_run: bool = True) -> dict[str, str]:
    """Ensure 'AksiaLegacy Author' maps to a system user.

    Many imported activities use this placeholder author name.
    Creates a system user if needed and adds it to the user map.
    """
    legacy_name = normalize_name("AksiaLegacy Author")
    if legacy_name in user_map:
        return user_map

    sb = get_supabase()

    # Check if user already exists
    existing = (
        sb.table("users")
        .select("id")
        .eq("display_name", "AksiaLegacy Author")
        .execute()
    )
    if existing.data:
        user_map[legacy_name] = existing.data[0]["id"]
        print(f"  Legacy author user exists: {existing.data[0]['id'][:8]}...")
        return user_map

    if dry_run:
        print("  [DRY-RUN] Would create 'AksiaLegacy Author' system user")
        user_map[legacy_name] = "dry-run-legacy-placeholder"
        return user_map

    legacy_email = "legacy-import@aksia.com"
    result = sb.table("users").insert({
        "entra_id": generate_entra_id(legacy_email),
        "display_name": "AksiaLegacy Author",
        "email": legacy_email,
        "is_active": False,
    }).execute()
    uid = result.data[0]["id"]
    user_map[legacy_name] = uid
    print(f"  Created legacy author user: {uid[:8]}...")
    return user_map


def import_activities(
    user_map: dict[str, str],
    *,
    dry_run: bool = True,
) -> dict[str, str]:
    """Stream activities CSV, import into activities table.

    Returns: {pa_activity_uuid: echo_activity_uuid} mapping.
    """
    csv.field_size_limit(sys.maxsize)

    pa_activity_map: dict[str, str] = {}
    batch_rows: list[dict] = []
    batch_pa_uuids: list[str] = []
    total_parsed = 0
    skipped_deleted = 0
    skipped_no_author = 0
    unmatched_authors: dict[str, int] = {}

    with open(ACTIVITIES_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_parsed += 1

            pa_uuid = clean_uuid(row.get("cr932_crmactivityid"))
            if not pa_uuid:
                continue

            # Skip deleted
            if safe_bool(row.get("cr932_isdeleted")):
                skipped_deleted += 1
                continue

            # Type mapping
            type_id = safe_int(row.get("cr932_type"))
            activity_type = ACTIVITY_TYPE_MAP.get(type_id, "note")

            # Date
            effective_date = safe_date(row.get("cr932_effectivedate"))
            if not effective_date:
                effective_date = date.today().isoformat()

            # Author (NOT NULL FK)
            author_name = row.get("cr932_author", "").strip()
            author_id = resolve_user(author_name, user_map)
            if not author_id:
                skipped_no_author += 1
                unmatched_authors[author_name] = unmatched_authors.get(author_name, 0) + 1
                continue

            # Details (NOT NULL — empty string OK)
            # Cap at 100K chars — tsvector index has 1MB limit and large
            # texts cause statement timeouts during index computation
            details = (row.get("cr932_descriptionplaintext") or "").strip()
            if len(details) > 100_000:
                details = details[:100_000]

            # Title
            title = safe_str(row.get("cr932_title"))

            activity_row = {
                "title": title,
                "effective_date": effective_date,
                "activity_type": activity_type,
                "author_id": author_id,
                "details": details,
                "is_deleted": False,
                "created_by": author_id,
            }

            batch_rows.append(activity_row)
            batch_pa_uuids.append(pa_uuid)

            # Flush batch
            if len(batch_rows) >= 10:
                if not dry_run:
                    results = _batch_insert("activities", batch_rows, batch_size=10)
                    for i, result in enumerate(results):
                        pa_activity_map[batch_pa_uuids[i]] = result["id"]
                batch_rows.clear()
                batch_pa_uuids.clear()

            if total_parsed % 5000 == 0:
                print(f"    ... processed {total_parsed} rows")

    # Flush remaining
    if batch_rows and not dry_run:
        results = _batch_insert("activities", batch_rows, batch_size=10)
        for i, result in enumerate(results):
            pa_activity_map[batch_pa_uuids[i]] = result["id"]

    # Report
    imported = len(pa_activity_map)
    would_import = total_parsed - skipped_deleted - skipped_no_author

    if dry_run:
        print(f"  [DRY-RUN] Would import {would_import} activities (total {total_parsed}, deleted {skipped_deleted}, no author {skipped_no_author})")
    else:
        print(f"  -> {imported} activities imported (total {total_parsed}, deleted {skipped_deleted}, no author {skipped_no_author})")

    if unmatched_authors:
        top = sorted(unmatched_authors.items(), key=lambda x: -x[1])[:10]
        print(f"    Unmatched authors ({len(unmatched_authors)} unique): {top}")

    return pa_activity_map


# ---------------------------------------------------------------------------
# EAV map rebuild (for standalone activity import)
# ---------------------------------------------------------------------------

def build_pa_entity_maps() -> tuple[dict[str, str], dict[str, str]]:
    """Rebuild PA UUID→Echo UUID maps from entity_custom_values.

    Used when activity import runs separately from entity import.
    Returns: (pa_org_map, pa_person_map)
    """
    sb = get_supabase()

    def _load_map(entity_type: str) -> dict[str, str]:
        # Find field_definition_id for power_apps_id
        fd = (
            sb.table("field_definitions")
            .select("id")
            .eq("entity_type", entity_type)
            .eq("field_name", "power_apps_id")
            .execute()
        )
        if not fd.data:
            print(f"    WARNING: No power_apps_id field_definition for {entity_type}")
            return {}
        fd_id = fd.data[0]["id"]

        # Paginate through EAV values
        result_map: dict[str, str] = {}
        offset = 0
        page_size = 1000
        while True:
            page = (
                sb.table("entity_custom_values")
                .select("entity_id, value_text")
                .eq("field_definition_id", fd_id)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            for row in page.data:
                pa_uuid = row["value_text"].strip().lower()
                result_map[pa_uuid] = row["entity_id"]
            if len(page.data) < page_size:
                break
            offset += page_size

        return result_map

    print("  Loading org PA map...")
    pa_org_map = _load_map("organization")
    print(f"    {len(pa_org_map)} entries")

    print("  Loading person PA map...")
    pa_person_map = _load_map("person")
    print(f"    {len(pa_person_map)} entries")

    return pa_org_map, pa_person_map


# ---------------------------------------------------------------------------
# Phase 10: Create Activity Links
# ---------------------------------------------------------------------------

def import_activity_links(
    activity_entities: list[dict],
    pa_activity_map: dict[str, str],
    pa_org_map: dict[str, str],
    pa_person_map: dict[str, str],
    *,
    dry_run: bool = True,
) -> tuple[int, int]:
    """Create activity_organization_links and activity_people_links.

    Returns: (org_link_count, person_link_count)
    """
    org_link_rows: list[dict] = []
    person_link_rows: list[dict] = []
    seen_org_links: set[tuple[str, str]] = set()
    seen_person_links: set[tuple[str, str]] = set()

    skipped_removed = 0
    skipped_no_activity = 0
    skipped_no_org = 0
    skipped_no_person = 0
    skipped_dup = 0

    for row in activity_entities:
        # Skip removed links
        if safe_bool(row.get("isremoved")):
            skipped_removed += 1
            continue

        # Resolve activity
        pa_activity_uuid = clean_uuid(row.get("activity"))
        if not pa_activity_uuid:
            continue
        echo_activity_id = pa_activity_map.get(pa_activity_uuid)
        if not echo_activity_id:
            skipped_no_activity += 1
            continue

        entity_type = safe_int(row.get("entity"))

        if entity_type == 1:
            # Org link
            pa_org_uuid = clean_uuid(row.get("organization"))
            if not pa_org_uuid:
                skipped_no_org += 1
                continue
            echo_org_id = pa_org_map.get(pa_org_uuid)
            if not echo_org_id:
                skipped_no_org += 1
                continue
            key = (echo_activity_id, echo_org_id)
            if key in seen_org_links:
                skipped_dup += 1
                continue
            seen_org_links.add(key)
            org_link_rows.append({
                "activity_id": echo_activity_id,
                "organization_id": echo_org_id,
            })

        elif entity_type == 2:
            # Person link
            pa_person_uuid = clean_uuid(row.get("person"))
            if not pa_person_uuid:
                skipped_no_person += 1
                continue
            echo_person_id = pa_person_map.get(pa_person_uuid)
            if not echo_person_id:
                skipped_no_person += 1
                continue
            key = (echo_activity_id, echo_person_id)
            if key in seen_person_links:
                skipped_dup += 1
                continue
            seen_person_links.add(key)
            person_link_rows.append({
                "activity_id": echo_activity_id,
                "person_id": echo_person_id,
            })

    if dry_run:
        print(f"  [DRY-RUN] Would create {len(org_link_rows)} org links, {len(person_link_rows)} person links")
        print(f"    Skipped: {skipped_removed} removed, {skipped_no_activity} no activity, {skipped_no_org} no org, {skipped_no_person} no person, {skipped_dup} duplicate")
        return (0, 0)

    # Insert org links
    org_count = 0
    if org_link_rows:
        print(f"  Inserting {len(org_link_rows)} activity_organization_links...")
        results = _batch_insert("activity_organization_links", org_link_rows, batch_size=50)
        org_count = len(results)

    # Insert person links
    person_count = 0
    if person_link_rows:
        print(f"  Inserting {len(person_link_rows)} activity_people_links...")
        results = _batch_insert("activity_people_links", person_link_rows, batch_size=50)
        person_count = len(results)

    print(f"  -> {org_count} org links, {person_count} person links created")
    print(f"    Skipped: {skipped_removed} removed, {skipped_no_activity} no activity, {skipped_no_org} no org, {skipped_no_person} no person, {skipped_dup} duplicate")

    return (org_count, person_count)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def import_echo_data(*, dry_run: bool = True) -> None:
    """Main entry point for CRM data import."""
    print("\n" + "=" * 60)
    print("Echo 2.0 — Steps 4-5: Import Core Entities + Activities")
    print("=" * 60)
    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"Mode: {mode}\n")

    # Phase 0: Setup
    print("Phase 0: Loading data...")
    data = load_excel_data(ECHO_DATA_XLSX)

    print("\n  Building user name->UUID map...")
    user_map = build_name_to_uuid_map()
    print(f"  {len(user_map)} name->UUID entries\n")

    # Print currency values for investigation
    currency_ids = set()
    for row in data.get("Leads", []):
        cid = safe_int(row.get("aksiallc_currency"))
        if cid is not None:
            currency_ids.add(cid)
    if currency_ids:
        print(f"  Currency IDs in leads data: {sorted(currency_ids)}")
        unmapped = currency_ids - set(CURRENCY_MAP.keys())
        if unmapped:
            print(f"  WARNING: Unmapped currency IDs: {sorted(unmapped)}")
    print()

    # Phase 1: Ensure reference_data
    print("Phase 1: Ensuring reference_data...")
    ensure_reference_data(dry_run=dry_run)

    # Collect all country codes we'll need
    all_countries = set()
    for row in data.get("Organizations", []):
        c = normalize_country(safe_str(row.get("country")))
        if c:
            all_countries.add(c)
    ensure_country_reference_data(all_countries, dry_run=dry_run)
    print()

    # Phase 2: Ensure field_definitions
    print("Phase 2: Ensuring power_apps_id field_definitions...")
    fd_ids = ensure_power_apps_field_defs(dry_run=dry_run)
    print()

    # Phase 3: Cleanup
    print("Phase 3: Cleaning up existing entity data...")
    cleanup_entity_data(dry_run=dry_run)
    print()

    # Phase 4: Import Organizations
    print(f"Phase 4: Importing Organizations ({len(data.get('Organizations', []))} rows)...")
    pa_org_map = import_organizations(data["Organizations"], user_map, dry_run=dry_run)
    print()

    # Phase 5: Import People
    print(f"Phase 5: Importing People ({len(data.get('People', []))} rows)...")
    pa_person_map = import_people(data["People"], pa_org_map, dry_run=dry_run)
    print()

    # Phase 6: Import Leads
    print(f"Phase 6: Importing Leads ({len(data.get('Leads', []))} rows)...")
    pa_lead_map = import_leads(data["Leads"], pa_org_map, user_map, dry_run=dry_run)
    print()

    # Phase 7: Import Contracts
    print(f"Phase 7: Importing Contracts ({len(data.get('Contracts', []))} rows)...")
    contracts_count = import_contracts(data["Contracts"], pa_org_map, pa_lead_map, dry_run=dry_run)
    print()

    # Phase 8: Store EAV power_apps_id values
    print("Phase 8: Storing EAV power_apps_id values...")
    eav_total = 0
    if not dry_run:
        for et, pa_map in [
            ("organization", pa_org_map),
            ("person", pa_person_map),
            ("lead", pa_lead_map),
        ]:
            count = store_eav_power_apps_ids(et, pa_map, fd_ids[et], dry_run=False)
            print(f"  {et}: {count} EAV values stored")
            eav_total += count
        # Contracts don't have a pa_contract_map built — build it now
        # (we didn't track pa_uuid→echo_uuid for contracts, but we can skip
        # since contracts are the leaf entity and not FK-referenced)
        print(f"  -> {eav_total} total EAV values stored")
    else:
        est = len(data.get("Organizations", [])) + len(data.get("People", [])) + len(data.get("Leads", [])) + len(data.get("Contracts", []))
        print(f"  [DRY-RUN] Would store ~{est} EAV power_apps_id values")
    print()

    # Phase 9: Import Activities from CSV
    print("Phase 9: Importing Activities from CSV...")
    user_map = ensure_legacy_author(user_map, dry_run=dry_run)
    pa_activity_map = import_activities(user_map, dry_run=dry_run)
    print()

    # Phase 10: Create Activity Links
    print(f"Phase 10: Creating Activity Links ({len(data.get('ActivityEntities', []))} rows)...")
    # Use in-memory maps when available; fall back to EAV query
    if pa_org_map and pa_person_map:
        pa_org_map_for_links = pa_org_map
        pa_person_map_for_links = pa_person_map
    elif not dry_run:
        print("  (Rebuilding PA maps from EAV...)")
        pa_org_map_for_links, pa_person_map_for_links = build_pa_entity_maps()
    else:
        pa_org_map_for_links = {}
        pa_person_map_for_links = {}

    org_links, person_links = import_activity_links(
        data.get("ActivityEntities", []),
        pa_activity_map,
        pa_org_map_for_links,
        pa_person_map_for_links,
        dry_run=dry_run,
    )
    print()

    # Summary
    print("=" * 60)
    if dry_run:
        print("DRY-RUN complete. Re-run with --apply to execute.")
    else:
        print("Import complete!")
        print(f"  Organizations: {len(pa_org_map)}")
        print(f"  People: {len(pa_person_map)}")
        print(f"  Leads: {len(pa_lead_map)}")
        print(f"  Contracts: {contracts_count}")
        print(f"  EAV values: {eav_total}")
        print(f"  Activities: {len(pa_activity_map)}")
        print(f"  Activity org links: {org_links}")
        print(f"  Activity person links: {person_links}")
    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import CRM data from EchoData.xlsx into Echo 2.0"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually import data (default is dry-run)",
    )
    args = parser.parse_args()

    import_echo_data(dry_run=not args.apply)

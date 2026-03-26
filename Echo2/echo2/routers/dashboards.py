"""Dashboards router — Personal, Advisory Pipeline, Capital Raise, Management."""

from collections import defaultdict
from datetime import date as date_type, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db.client import get_supabase
from db.helpers import get_reference_data, batch_resolve_users, batch_resolve_orgs, is_overdue
from dependencies import CurrentUser, get_current_user, require_role

router = APIRouter(prefix="/dashboards", tags=["dashboards"])
templates = Jinja2Templates(directory="templates")

# Lead stage ordering (mirrored from leads.py — each router is self-contained)
LEAD_STAGE_ORDER = ["exploratory", "radar", "focus", "verbal_mandate"]
LEAD_INACTIVE_STAGES = {"won", "lost_dropped_out", "lost_selected_other", "lost_nobody_hired"}
LEAD_LOST_STAGES = {"lost_dropped_out", "lost_selected_other", "lost_nobody_hired"}
LEAD_ALL_STAGES = LEAD_STAGE_ORDER + ["won"] + list(LEAD_LOST_STAGES)

# Fund prospect stage ordering (mirrored from fund_prospects.py)
FP_STAGE_ORDER = [
    "target_identified", "intro_scheduled", "initial_meeting_complete",
    "ddq_materials_sent", "due_diligence", "ic_review",
    "soft_circle", "legal_docs", "closed", "declined",
]

# Color maps
LEAD_STAGE_COLORS = {
    "exploratory": "bg-gray-400",
    "radar": "bg-blue-400",
    "focus": "bg-yellow-400",
    "verbal_mandate": "bg-purple-400",
    "won": "bg-green-400",
    "lost_dropped_out": "bg-red-400",
    "lost_selected_other": "bg-red-300",
    "lost_nobody_hired": "bg-red-200",
}

FP_STAGE_COLORS = {
    "target_identified": "bg-gray-400",
    "intro_scheduled": "bg-blue-400",
    "initial_meeting_complete": "bg-indigo-400",
    "ddq_materials_sent": "bg-cyan-400",
    "due_diligence": "bg-yellow-400",
    "ic_review": "bg-orange-400",
    "soft_circle": "bg-purple-400",
    "legal_docs": "bg-pink-400",
    "closed": "bg-green-400",
    "declined": "bg-red-400",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val) -> float:
    """Convert to float safely, defaulting to 0.0."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _pct(numerator: float, denominator: float) -> float:
    """Calculate percentage with safety."""
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator * 100, 1)


def _fmt_currency(val: float) -> str:
    """Format as currency with commas, no decimals."""
    return '{:,.0f}'.format(val)


def _fmt_mn(val: float) -> str:
    """Format as $M with 1 decimal."""
    return '{:,.1f}'.format(val)


def _batch_resolve_linked_records(tasks: list[dict]) -> dict:
    """Resolve linked records for tasks in batch. Returns dict keyed by (type, id)."""
    sb = get_supabase()
    results = {}
    by_type: dict[str, set] = {}
    for t in tasks:
        rt = t.get("linked_record_type")
        ri = t.get("linked_record_id")
        if rt and ri:
            by_type.setdefault(rt, set()).add(str(ri))

    if "lead" in by_type:
        ids = list(by_type["lead"])
        resp = sb.table("leads").select("id, organization_id, summary").in_("id", ids).execute()
        org_ids_needed = {str(r["organization_id"]) for r in (resp.data or []) if r.get("organization_id")}
        org_names = {}
        if org_ids_needed:
            org_resp = sb.table("organizations").select("id, company_name").in_("id", list(org_ids_needed)).execute()
            org_names = {str(o["id"]): o["company_name"] for o in (org_resp.data or [])}
        for r in (resp.data or []):
            org_name = org_names.get(str(r.get("organization_id", "")), "Unknown Org")
            results[("lead", str(r["id"]))] = {"name": org_name, "url": f"/leads/{r['id']}"}

    if "fund_prospect" in by_type:
        # Legacy: fund_prospect linked records now point to leads table
        # (migration script updates references, but handle any stragglers)
        ids = list(by_type["fund_prospect"])
        # Try leads table first (migrated records)
        resp = sb.table("leads").select("id, organization_id, fund_id, lead_type").in_("id", ids).execute()
        found_ids = {str(r["id"]) for r in (resp.data or [])}
        # Fall back to fund_prospects table for unmigrated records
        remaining_ids = [i for i in ids if i not in found_ids]
        fp_rows = []
        if remaining_ids:
            fp_resp = sb.table("fund_prospects").select("id, organization_id, fund_id").in_("id", remaining_ids).execute()
            fp_rows = fp_resp.data or []

        all_rows = list(resp.data or []) + fp_rows
        org_ids_needed = {str(r["organization_id"]) for r in all_rows if r.get("organization_id")}
        fund_ids_needed = {str(r["fund_id"]) for r in all_rows if r.get("fund_id")}
        org_names = {}
        fund_tickers = {}
        if org_ids_needed:
            org_resp = sb.table("organizations").select("id, company_name").in_("id", list(org_ids_needed)).execute()
            org_names = {str(o["id"]): o["company_name"] for o in (org_resp.data or [])}
        if fund_ids_needed:
            fund_resp = sb.table("funds").select("id, ticker").in_("id", list(fund_ids_needed)).execute()
            fund_tickers = {str(f["id"]): f["ticker"] for f in (fund_resp.data or [])}
        for r in all_rows:
            org_name = org_names.get(str(r.get("organization_id", "")), "Unknown Org")
            ticker = fund_tickers.get(str(r.get("fund_id", "")), "?")
            rid = str(r["id"])
            url = f"/leads/{rid}" if rid in found_ids else f"/leads/{rid}"
            results[("fund_prospect", rid)] = {"name": f"{org_name} ({ticker})", "url": url}

    if "activity" in by_type:
        ids = list(by_type["activity"])
        resp = sb.table("activities").select("id, title").in_("id", ids).execute()
        for r in (resp.data or []):
            results[("activity", str(r["id"]))] = {"name": r.get("title") or "Untitled", "url": f"/activities/{r['id']}"}

    if "organization" in by_type:
        ids = list(by_type["organization"])
        resp = sb.table("organizations").select("id, company_name").in_("id", ids).execute()
        for r in (resp.data or []):
            results[("organization", str(r["id"]))] = {"name": r["company_name"], "url": f"/organizations/{r['id']}"}

    if "person" in by_type:
        ids = list(by_type["person"])
        resp = sb.table("people").select("id, first_name, last_name").in_("id", ids).execute()
        for r in (resp.data or []):
            results[("person", str(r["id"]))] = {"name": f"{r['first_name']} {r['last_name']}", "url": f"/people/{r['id']}"}

    return results


# ---------------------------------------------------------------------------
# PERSONAL DASHBOARD WIDGETS (HTMX partials for homepage)
# ---------------------------------------------------------------------------

@router.get("/personal/widgets/pipeline-summary", response_class=HTMLResponse)
async def widget_pipeline_summary(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX: pipeline summary cards for the current user's leads."""
    sb = get_supabase()
    resp = (
        sb.table("leads")
        .select("rating, expected_revenue")
        .eq("is_deleted", False)
        .eq("aksia_owner_id", str(current_user.id))
        .execute()
    )
    leads = resp.data or []

    # Group by stage (active stages only)
    stage_groups = defaultdict(lambda: {"count": 0, "total_revenue": 0.0})
    for lead in leads:
        rating = lead.get("rating", "exploratory")
        if rating in LEAD_INACTIVE_STAGES:
            continue
        stage_groups[rating]["count"] += 1
        stage_groups[rating]["total_revenue"] += _safe_float(lead.get("expected_revenue"))

    stage_labels = {s["value"]: s["label"] for s in get_reference_data("lead_stage")}
    stages = []
    for stage_val in LEAD_STAGE_ORDER:
        g = stage_groups.get(stage_val, {"count": 0, "total_revenue": 0.0})
        stages.append({
            "stage": stage_val,
            "stage_label": stage_labels.get(stage_val, stage_val.replace("_", " ").title()),
            "count": g["count"],
            "total_revenue": g["total_revenue"],
            "total_revenue_formatted": _fmt_currency(g["total_revenue"]),
            "color": LEAD_STAGE_COLORS.get(stage_val, "bg-gray-400"),
        })

    return templates.TemplateResponse("dashboards/_widget_pipeline_summary.html", {
        "request": request,
        "stages": stages,
    })


@router.get("/personal/widgets/tasks", response_class=HTMLResponse)
async def widget_tasks(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX: open tasks for the current user."""
    sb = get_supabase()
    resp = (
        sb.table("tasks")
        .select("id, title, due_date, status, linked_record_type, linked_record_id, notes, source")
        .eq("is_deleted", False)
        .eq("assigned_to", str(current_user.id))
        .in_("status", ["open", "in_progress"])
        .order("due_date", nullsfirst=False)
        .limit(10)
        .execute()
    )
    tasks = resp.data or []

    # Enrich
    record_map = _batch_resolve_linked_records(tasks)
    for task in tasks:
        task["is_overdue"] = is_overdue(task)
        key = (task.get("linked_record_type"), str(task.get("linked_record_id", "")))
        task["linked_info"] = record_map.get(key)

    return templates.TemplateResponse("dashboards/_widget_tasks.html", {
        "request": request,
        "tasks": tasks,
    })


@router.get("/personal/widgets/leads", response_class=HTMLResponse)
async def widget_leads(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX: open leads for the current user."""
    sb = get_supabase()
    # Exclude inactive stages
    inactive = list(LEAD_INACTIVE_STAGES)
    resp = (
        sb.table("leads")
        .select("id, organization_id, rating, service_type, expected_revenue")
        .eq("is_deleted", False)
        .eq("aksia_owner_id", str(current_user.id))
        .not_.in_("rating", inactive)
        .order("expected_revenue", desc=True, nullsfirst=False)
        .limit(10)
        .execute()
    )
    leads = resp.data or []

    # Batch resolve org names
    org_ids = list({str(l["organization_id"]) for l in leads if l.get("organization_id")})
    org_map = batch_resolve_orgs(org_ids)

    stage_labels = {s["value"]: s["label"] for s in get_reference_data("lead_stage")}

    for lead in leads:
        org = org_map.get(str(lead.get("organization_id", "")), {})
        lead["org_name"] = org.get("company_name", "—") if isinstance(org, dict) else "—"
        lead["stage_label"] = stage_labels.get(lead.get("rating", ""), lead.get("rating", "").replace("_", " ").title())
        lead["stage_color"] = LEAD_STAGE_COLORS.get(lead.get("rating", ""), "bg-gray-400")
        lead["revenue_formatted"] = _fmt_currency(_safe_float(lead.get("expected_revenue"))) if lead.get("expected_revenue") else "—"

    return templates.TemplateResponse("dashboards/_widget_leads.html", {
        "request": request,
        "leads": leads,
    })


@router.get("/personal/widgets/activities", response_class=HTMLResponse)
async def widget_activities(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """HTMX: recent activities for the current user."""
    sb = get_supabase()
    resp = (
        sb.table("activities")
        .select("id, title, effective_date, activity_type")
        .eq("is_deleted", False)
        .eq("author_id", str(current_user.id))
        .order("effective_date", desc=True)
        .limit(10)
        .execute()
    )
    activities = resp.data or []

    # Resolve org links
    if activities:
        act_ids = [str(a["id"]) for a in activities]
        links_resp = (
            sb.table("activity_organization_links")
            .select("activity_id, organization_id")
            .in_("activity_id", act_ids)
            .execute()
        )
        links = links_resp.data or []
        # Group org ids by activity
        act_orgs: dict[str, list[str]] = defaultdict(list)
        for link in links:
            act_orgs[str(link["activity_id"])].append(str(link["organization_id"]))

        # Batch resolve all org names
        all_org_ids = list({oid for oids in act_orgs.values() for oid in oids})
        org_map = batch_resolve_orgs(all_org_ids)

        for act in activities:
            org_ids = act_orgs.get(str(act["id"]), [])
            act["org_names"] = ", ".join(
                org_map.get(oid, {}).get("company_name", "?") if isinstance(org_map.get(oid), dict) else "?"
                for oid in org_ids[:3]
            )
            if len(org_ids) > 3:
                act["org_names"] += f" +{len(org_ids) - 3} more"

    type_colors = {
        "call": "bg-blue-100 text-blue-800",
        "meeting": "bg-purple-100 text-purple-800",
        "email": "bg-green-100 text-green-800",
        "note": "bg-gray-100 text-gray-600",
        "conference": "bg-yellow-100 text-yellow-800",
        "webinar": "bg-indigo-100 text-indigo-800",
    }

    return templates.TemplateResponse("dashboards/_widget_activities.html", {
        "request": request,
        "activities": activities,
        "type_colors": type_colors,
    })


@router.get("/personal/widgets/my-coverage", response_class=HTMLResponse)
async def widget_my_coverage(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Widget: counts of orgs, people, leads (advisory + fundraise) under user's coverage."""
    try:
        sb = get_supabase()

        # Count people where coverage_owner = current user
        people_resp = sb.table("people").select("id", count="exact").eq("is_deleted", False).eq("coverage_owner", str(current_user.id)).execute()
        people_count = people_resp.count or 0

        # Count advisory leads where aksia_owner = current user
        advisory_leads_resp = sb.table("leads").select("id", count="exact").eq("is_deleted", False).eq("aksia_owner_id", str(current_user.id)).eq("lead_type", "advisory").execute()
        advisory_leads_count = advisory_leads_resp.count or 0

        # Count fundraise/product leads where aksia_owner = current user
        fundraise_leads_resp = sb.table("leads").select("id", count="exact").eq("is_deleted", False).eq("aksia_owner_id", str(current_user.id)).in_("lead_type", ["fundraise", "product"]).execute()
        fundraise_leads_count = fundraise_leads_resp.count or 0

        # Count orgs (via coverage on people + leads)
        my_org_ids = set()
        if people_count > 0:
            covered_people = sb.table("people").select("id").eq("coverage_owner", str(current_user.id)).eq("is_deleted", False).execute()
            person_ids = [str(p["id"]) for p in (covered_people.data or [])]
            if person_ids:
                pol_resp = sb.table("person_organization_links").select("organization_id").in_("person_id", person_ids).execute()
                my_org_ids |= {str(r["organization_id"]) for r in (pol_resp.data or [])}
        all_leads_count = advisory_leads_count + fundraise_leads_count
        if all_leads_count > 0:
            owned_leads = sb.table("leads").select("organization_id").eq("aksia_owner_id", str(current_user.id)).eq("is_deleted", False).execute()
            my_org_ids |= {str(l["organization_id"]) for l in (owned_leads.data or []) if l.get("organization_id")}
        org_count = len(my_org_ids)

        context = {
            "request": request,
            "org_count": org_count,
            "people_count": people_count,
            "leads_count": advisory_leads_count,
            "fundraise_leads_count": fundraise_leads_count,
        }
        return templates.TemplateResponse("dashboards/_widget_my_coverage.html", context)
    except Exception as e:
        import traceback; traceback.print_exc()
        return HTMLResponse(
            '<div class="text-center py-4 text-sm text-red-500">'
            f'<p>Unable to load coverage data.</p>'
            f'<p class="text-xs text-gray-400 mt-1">{type(e).__name__}: {e}</p></div>'
        )


@router.get("/personal/widgets/missing-info", response_class=HTMLResponse)
async def widget_missing_info(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Widget: people/leads under coverage missing key fields."""
    try:
        sb = get_supabase()

        # People missing email or phone
        people_resp = sb.table("people").select("id, first_name, last_name, email, phone").eq("is_deleted", False).eq("coverage_owner", str(current_user.id)).execute()
        all_people = people_resp.data or []
        people_missing = [p for p in all_people if not p.get("email") or not p.get("phone")]

        # Leads missing expected_revenue or service_type
        leads_resp = sb.table("leads").select("id, organization_id, service_type, expected_revenue, summary").eq("is_deleted", False).eq("aksia_owner_id", str(current_user.id)).execute()
        all_leads = leads_resp.data or []
        leads_missing = [l for l in all_leads if not l.get("expected_revenue") or not l.get("service_type")]

        # Resolve org names for leads
        lead_org_ids = list({str(l["organization_id"]) for l in leads_missing if l.get("organization_id")})
        org_names = {}
        if lead_org_ids:
            orgs_resp = sb.table("organizations").select("id, company_name").in_("id", lead_org_ids).execute()
            org_names = {str(o["id"]): o["company_name"] for o in (orgs_resp.data or [])}

        for lead in leads_missing:
            lead["org_name"] = org_names.get(str(lead.get("organization_id")), "Unknown Org")

        context = {
            "request": request,
            "people_missing": people_missing[:5],
            "people_missing_count": len(people_missing),
            "leads_missing": leads_missing[:5],
            "leads_missing_count": len(leads_missing),
        }
        return templates.TemplateResponse("dashboards/_widget_missing_info.html", context)
    except Exception as e:
        import traceback; traceback.print_exc()
        return HTMLResponse(
            '<div class="text-center py-4 text-sm text-red-500">'
            f'<p>Unable to load missing info data.</p>'
            f'<p class="text-xs text-gray-400 mt-1">{type(e).__name__}: {e}</p></div>'
        )


@router.get("/personal/widgets/stale-contacts", response_class=HTMLResponse)
async def widget_stale_contacts(
    request: Request,
    days: int = Query(90),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Widget: people under coverage with no activity in X days."""
    try:
        sb = get_supabase()
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # Get all covered people
        people_resp = sb.table("people").select("id, first_name, last_name, email").eq("is_deleted", False).eq("coverage_owner", str(current_user.id)).execute()
        covered_people = people_resp.data or []

        if not covered_people:
            return templates.TemplateResponse("dashboards/_widget_stale_contacts.html", {
                "request": request, "stale_contacts": [], "stale_count": 0
            })

        person_ids = [str(p["id"]) for p in covered_people]

        # Get all activity links for these people
        apl_resp = sb.table("activity_people_links").select("person_id, activity_id").in_("person_id", person_ids).execute()
        person_activity_ids = {}
        for link in (apl_resp.data or []):
            pid = str(link["person_id"])
            if pid not in person_activity_ids:
                person_activity_ids[pid] = []
            person_activity_ids[pid].append(str(link["activity_id"]))

        # Get activity dates for all linked activities
        all_activity_ids = []
        for aids in person_activity_ids.values():
            all_activity_ids.extend(aids)
        all_activity_ids = list(set(all_activity_ids))

        activity_dates = {}
        if all_activity_ids:
            # Batch in chunks of 100 to avoid query limits
            for i in range(0, len(all_activity_ids), 100):
                chunk = all_activity_ids[i:i+100]
                act_resp = sb.table("activities").select("id, effective_date").in_("id", chunk).eq("is_deleted", False).execute()
                for a in (act_resp.data or []):
                    activity_dates[str(a["id"])] = a.get("effective_date")

        # Find most recent activity date per person
        stale_contacts = []
        for person in covered_people:
            pid = str(person["id"])
            aids = person_activity_ids.get(pid, [])
            if not aids:
                # No activities at all
                person["last_activity_date"] = None
                person["days_since"] = None
                stale_contacts.append(person)
            else:
                dates = [activity_dates.get(aid) for aid in aids if activity_dates.get(aid)]
                if dates:
                    most_recent = max(dates)
                    if most_recent < cutoff_date:
                        person["last_activity_date"] = most_recent
                        delta = datetime.now() - datetime.strptime(most_recent[:10], "%Y-%m-%d")
                        person["days_since"] = delta.days
                        stale_contacts.append(person)
                else:
                    person["last_activity_date"] = None
                    person["days_since"] = None
                    stale_contacts.append(person)

        # Sort: no activity first, then oldest first
        stale_contacts.sort(key=lambda x: x.get("last_activity_date") or "0000-00-00")

        # Resolve primary orgs
        stale_person_ids = [str(p["id"]) for p in stale_contacts[:10]]
        if stale_person_ids:
            pol_resp = sb.table("person_organization_links").select("person_id, organization:organizations(company_name)").in_("person_id", stale_person_ids).eq("link_type", "primary").execute()
            org_map = {}
            for r in (pol_resp.data or []):
                if r.get("organization"):
                    org_map[str(r["person_id"])] = r["organization"]["company_name"]
            for person in stale_contacts[:10]:
                person["org_name"] = org_map.get(str(person["id"]), "")

        context = {
            "request": request,
            "stale_contacts": stale_contacts[:10],
            "stale_count": len(stale_contacts),
        }
        return templates.TemplateResponse("dashboards/_widget_stale_contacts.html", context)
    except Exception as e:
        import traceback; traceback.print_exc()
        return HTMLResponse(
            '<div class="text-center py-4 text-sm text-red-500">'
            f'<p>Unable to load stale contacts data.</p>'
            f'<p class="text-xs text-gray-400 mt-1">{type(e).__name__}: {e}</p></div>'
        )


# ---------------------------------------------------------------------------
# ADVISORY PIPELINE — shared data loader
# ---------------------------------------------------------------------------

def _get_groupable_fields(entity_type: str = "lead") -> list[dict]:
    """Return fields suitable for group-by in pipeline dashboards."""
    from db.field_service import get_field_definitions
    field_defs = get_field_definitions(entity_type, active_only=True)
    groupable = []
    for fd in field_defs:
        if fd["field_type"] in ("dropdown", "multi_select"):
            groupable.append({
                "value": fd["field_name"],
                "label": fd["display_name"],
                "field_type": fd["field_type"],
            })
    # Always include non-dropdown groupings
    groupable.append({"value": "owner", "label": "Owner", "field_type": "lookup"})
    groupable.append({"value": "fund", "label": "Fund", "field_type": "lookup"})
    return groupable


def _load_advisory_leads(
    service: str = "",
    asset_class: str = "",
    owner: str = "",
    org_type: str = "",
    date_from: str = "",
    date_to: str = "",
    active_filter: str = "active",
    stage: str = "",
) -> list[dict]:
    """Load advisory leads with filters. Returns list of lead dicts."""
    sb = get_supabase()
    query = (
        sb.table("leads")
        .select("id, organization_id, rating, service_type, asset_classes, "
                "expected_revenue, expected_yr1_flar, expected_longterm_flar, "
                "aksia_owner_id, start_date, end_date, relationship, summary, fund_id")
        .eq("is_deleted", False)
    )
    if service:
        query = query.eq("service_type", service)
    if owner:
        query = query.eq("aksia_owner_id", owner)
    if date_from:
        query = query.gte("start_date", date_from)
    if date_to:
        query = query.lte("start_date", date_to)
    if org_type:
        org_resp = (
            sb.table("organizations")
            .select("id")
            .eq("is_deleted", False)
            .eq("organization_type", org_type)
            .execute()
        )
        org_type_ids = [o["id"] for o in (org_resp.data or [])]
        if org_type_ids:
            query = query.in_("organization_id", org_type_ids)
        else:
            query = query.eq("organization_id", "00000000-0000-0000-0000-000000000000")
    resp = query.execute()
    all_leads = resp.data or []
    if asset_class:
        all_leads = [l for l in all_leads if asset_class in (l.get("asset_classes") or [])]

    # Apply active/inactive filter
    if active_filter == "active":
        all_leads = [l for l in all_leads if l.get("rating") not in LEAD_INACTIVE_STAGES]
    elif active_filter == "inactive":
        all_leads = [l for l in all_leads if l.get("rating") in LEAD_INACTIVE_STAGES]
    # "all" => no filtering

    # Apply stage filter
    if stage:
        all_leads = [l for l in all_leads if l.get("rating") == stage]

    return all_leads


def _build_advisory_funnel(all_leads: list[dict]) -> list[dict]:
    """Build vertical funnel stages for advisory conversion funnel."""
    total = len(all_leads)
    active = [l for l in all_leads if l.get("rating") not in LEAD_INACTIVE_STAGES]
    won = [l for l in all_leads if l.get("rating") == "won"]
    lost = [l for l in all_leads if l.get("rating") in LEAD_LOST_STAGES]
    if total == 0:
        return []
    return [
        {"label": "Total Leads", "count": total, "pct": 100.0, "bg_class": "bg-blue-500"},
        {"label": "Active", "count": len(active), "pct": _pct(len(active), total), "bg_class": "bg-indigo-500"},
        {"label": "Won", "count": len(won), "pct": _pct(len(won), total), "bg_class": "bg-green-500"},
        {"label": "Lost", "count": len(lost), "pct": _pct(len(lost), total), "bg_class": "bg-red-500"},
    ]


def _group_advisory_leads(all_leads: list[dict], group_by: str) -> list[dict]:
    """Group advisory leads by a dimension, returning bar chart data."""
    stage_labels = {s["value"]: s["label"] for s in get_reference_data("lead_stage")}
    service_type_labels = {s["value"]: s["label"] for s in get_reference_data("service_type")}
    ac_labels = {a["value"]: a["label"] for a in get_reference_data("asset_class")}

    groups: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_revenue": 0.0})

    color_cycle = ["bg-blue-400", "bg-indigo-400", "bg-purple-400", "bg-cyan-400",
                   "bg-teal-400", "bg-yellow-400", "bg-orange-400", "bg-pink-400",
                   "bg-green-400", "bg-red-400", "bg-gray-400"]

    # Detect if group_by is a multi_select field (for array expansion)
    _groupable_cache = _get_groupable_fields("lead")
    _groupable_map = {gf["value"]: gf for gf in _groupable_cache}
    _is_multi_select = _groupable_map.get(group_by, {}).get("field_type") == "multi_select"

    for lead in all_leads:
        if group_by == "stage":
            key = lead.get("rating", "exploratory")
        elif group_by == "service_type":
            key = lead.get("service_type") or "unspecified"
        elif group_by == "asset_class":
            acs = lead.get("asset_classes") or []
            for ac in (acs or ["unspecified"]):
                groups[ac]["count"] += 1
                groups[ac]["total_revenue"] += _safe_float(lead.get("expected_revenue"))
            continue
        elif group_by == "owner":
            key = str(lead.get("aksia_owner_id") or "unassigned")
        elif group_by == "fund":
            key = str(lead.get("fund_id") or "none")
        else:
            # Generic field — handle multi_select arrays
            raw_val = lead.get(group_by)
            if _is_multi_select and isinstance(raw_val, list):
                for mv in (raw_val or ["Unspecified"]):
                    groups[str(mv)]["count"] += 1
                    groups[str(mv)]["total_revenue"] += _safe_float(lead.get("expected_revenue"))
                continue
            else:
                key = str(raw_val or "Unspecified")
        groups[key]["count"] += 1
        groups[key]["total_revenue"] += _safe_float(lead.get("expected_revenue"))

    # Resolve labels
    if group_by == "stage":
        label_map = stage_labels
        ordered_keys = [s for s in LEAD_ALL_STAGES if s in groups]
        color_map = LEAD_STAGE_COLORS
    elif group_by == "service_type":
        label_map = service_type_labels
        ordered_keys = sorted(groups.keys(), key=lambda k: groups[k]["total_revenue"], reverse=True)
        color_map = {}
    elif group_by == "asset_class":
        label_map = ac_labels
        ordered_keys = sorted(groups.keys(), key=lambda k: groups[k]["total_revenue"], reverse=True)
        color_map = {}
    elif group_by == "owner":
        user_ids = [k for k in groups.keys() if k != "unassigned"]
        user_names = batch_resolve_users(user_ids)
        label_map = {k: user_names.get(k, "Unknown") for k in user_ids}
        label_map["unassigned"] = "Unassigned"
        ordered_keys = sorted(groups.keys(), key=lambda k: groups[k]["total_revenue"], reverse=True)
        color_map = {}
    elif group_by == "fund":
        sb = get_supabase()
        fund_ids = [k for k in groups.keys() if k != "none"]
        fund_names: dict[str, str] = {}
        if fund_ids:
            fr = sb.table("funds").select("id, ticker, fund_name").in_("id", fund_ids).execute()
            fund_names = {str(f["id"]): f.get("ticker") or f.get("fund_name", "?") for f in (fr.data or [])}
        label_map = {k: fund_names.get(k, "Unknown Fund") for k in fund_ids}
        label_map["none"] = "No Fund"
        ordered_keys = sorted(groups.keys(), key=lambda k: groups[k]["total_revenue"], reverse=True)
        color_map = {}
    else:
        # Generic field — try to resolve labels from reference_data
        ref_data = get_reference_data(group_by)
        if ref_data:
            label_map = {r["value"]: r["label"] for r in ref_data}
        else:
            label_map = {}
        ordered_keys = sorted(groups.keys(), key=lambda k: groups[k]["total_revenue"], reverse=True)
        color_map = {}

    max_revenue = max((g["total_revenue"] for g in groups.values()), default=1) or 1

    bars = []
    for idx, key in enumerate(ordered_keys):
        g = groups[key]
        if g["count"] == 0:
            continue
        bars.append({
            "key": key,
            "label": label_map.get(key, key.replace("_", " ").title()),
            "count": g["count"],
            "total_revenue": g["total_revenue"],
            "revenue_fmt": _fmt_currency(g["total_revenue"]),
            "bar_pct": _pct(g["total_revenue"], max_revenue),
            "color": color_map.get(key, color_cycle[idx % len(color_cycle)]),
        })
    return bars


# ---------------------------------------------------------------------------
# ADVISORY PIPELINE DASHBOARD — GET /dashboards/advisory-pipeline
# ---------------------------------------------------------------------------

@router.get("/advisory-pipeline", response_class=HTMLResponse)
async def advisory_pipeline(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: str = Query(""),
    asset_class: str = Query("", alias="asset_class"),
    owner: str = Query(""),
    org_type: str = Query("", alias="org_type"),
    date_from: str = Query("", alias="from"),
    date_to: str = Query("", alias="to"),
    active_filter: str = Query("active", alias="active_filter"),
    stage: str = Query("", alias="stage"),
):
    """Advisory Pipeline Dashboard with filters."""
    sb = get_supabase()

    all_leads = _load_advisory_leads(service, asset_class, owner, org_type, date_from, date_to, active_filter, stage)

    # --- Aggregate ---
    stage_labels = {s["value"]: s["label"] for s in get_reference_data("lead_stage")}
    service_type_labels = {s["value"]: s["label"] for s in get_reference_data("service_type")}
    ac_labels = {a["value"]: a["label"] for a in get_reference_data("asset_class")}

    active_leads = [l for l in all_leads if l.get("rating") not in LEAD_INACTIVE_STAGES]
    won_leads = [l for l in all_leads if l.get("rating") == "won"]
    lost_leads = [l for l in all_leads if l.get("rating") in LEAD_LOST_STAGES]

    # 1. KPI Summary
    total_active = len(active_leads)
    total_pipeline_revenue = sum(_safe_float(l.get("expected_revenue")) for l in active_leads)
    total_yr1_flar = sum(_safe_float(l.get("expected_yr1_flar")) for l in active_leads)
    won_count = len(won_leads)
    lost_count = len(lost_leads)
    win_rate = _pct(won_count, won_count + lost_count) if (won_count + lost_count) > 0 else 0.0

    # 2. Pipeline by Stage (default group-by)
    pipeline_by_stage = _group_advisory_leads(all_leads, "stage")

    # 3. Revenue by Service Type
    svc_groups = defaultdict(lambda: {"count": 0, "total_revenue": 0.0})
    for lead in active_leads:
        svc = lead.get("service_type") or "unspecified"
        svc_groups[svc]["count"] += 1
        svc_groups[svc]["total_revenue"] += _safe_float(lead.get("expected_revenue"))

    max_svc_rev = max((g["total_revenue"] for g in svc_groups.values()), default=1) or 1
    revenue_by_service = []
    for svc, g in sorted(svc_groups.items(), key=lambda x: x[1]["total_revenue"], reverse=True):
        revenue_by_service.append({
            "service_type": svc,
            "label": service_type_labels.get(svc, svc.replace("_", " ").title()),
            "count": g["count"],
            "total_revenue": g["total_revenue"],
            "revenue_fmt": _fmt_currency(g["total_revenue"]),
            "bar_pct": _pct(g["total_revenue"], max_svc_rev),
        })

    # 4. FLAR by Asset Class
    flar_by_ac = defaultdict(lambda: {"yr1": 0.0, "longterm": 0.0})
    for lead in active_leads:
        acs = lead.get("asset_classes") or []
        yr1 = _safe_float(lead.get("expected_yr1_flar"))
        lt = _safe_float(lead.get("expected_longterm_flar"))
        for ac in acs:
            flar_by_ac[ac]["yr1"] += yr1
            flar_by_ac[ac]["longterm"] += lt

    flar_analysis = [
        {
            "asset_class": ac,
            "label": ac_labels.get(ac, ac.replace("_", " ").title()),
            "yr1": v["yr1"],
            "yr1_fmt": _fmt_currency(v["yr1"]),
            "longterm": v["longterm"],
            "longterm_fmt": _fmt_currency(v["longterm"]),
        }
        for ac, v in sorted(flar_by_ac.items(), key=lambda x: x[1]["longterm"], reverse=True)
    ]

    # 5. Conversion Funnel (vertical)
    funnel_stages = _build_advisory_funnel(all_leads)

    # 6. Owner Coverage
    owner_data = defaultdict(lambda: {"active": 0, "won": 0, "pipeline_revenue": 0.0})
    for lead in all_leads:
        oid = str(lead.get("aksia_owner_id", ""))
        if not oid:
            continue
        rating = lead.get("rating", "")
        if rating not in LEAD_INACTIVE_STAGES:
            owner_data[oid]["active"] += 1
            owner_data[oid]["pipeline_revenue"] += _safe_float(lead.get("expected_revenue"))
        elif rating == "won":
            owner_data[oid]["won"] += 1

    user_names = batch_resolve_users(list(owner_data.keys()))
    owner_coverage = [
        {
            "owner_name": user_names.get(k, "Unknown"),
            "active": v["active"],
            "won": v["won"],
            "pipeline_revenue": v["pipeline_revenue"],
            "revenue_fmt": _fmt_currency(v["pipeline_revenue"]),
            "avg_revenue": _fmt_currency(v["pipeline_revenue"] / v["active"]) if v["active"] > 0 else "—",
        }
        for k, v in sorted(owner_data.items(), key=lambda x: x[1]["pipeline_revenue"], reverse=True)
    ]

    # --- Reference data for filter dropdowns ---
    service_types = get_reference_data("service_type")
    asset_classes = get_reference_data("asset_class")
    org_types = get_reference_data("organization_type")
    all_stages = get_reference_data("lead_stage")
    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).order("display_name").execute()

    last_refreshed = datetime.now().strftime("%b %d, %Y %I:%M %p")

    # C2: Dynamic groupable fields
    groupable_fields = _get_groupable_fields("lead")

    context = {
        "request": request,
        "user": current_user,
        "last_refreshed": last_refreshed,
        # KPI
        "total_active": total_active,
        "total_pipeline_revenue": _fmt_currency(total_pipeline_revenue),
        "total_yr1_flar": _fmt_currency(total_yr1_flar),
        "win_rate": win_rate,
        "won_count": won_count,
        "lost_count": lost_count,
        # Pipeline chart (default: grouped by stage)
        "pipeline_by_stage": pipeline_by_stage,
        "group_by": "stage",
        # Revenue by service
        "revenue_by_service": revenue_by_service,
        # FLAR
        "flar_analysis": flar_analysis,
        # Funnel (vertical)
        "funnel_stages": funnel_stages,
        "total_leads": len(all_leads),
        "total_active_count": total_active,
        "active_pct": _pct(total_active, len(all_leads)),
        "won_pct": _pct(won_count, len(all_leads)),
        "lost_pct": _pct(lost_count, len(all_leads)),
        # Owner coverage
        "owner_coverage": owner_coverage,
        # Filters
        "service_types": service_types,
        "asset_classes": asset_classes,
        "org_types": org_types,
        "all_stages": all_stages,
        "users": users_resp.data or [],
        "filter_service": service,
        "filter_asset_class": asset_class,
        "filter_owner": owner,
        "filter_org_type": org_type,
        "filter_date_from": date_from,
        "filter_date_to": date_to,
        "filter_active": active_filter,
        "filter_stage": stage,
        # C2: Dynamic group-by fields
        "groupable_fields": groupable_fields,
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("dashboards/_advisory_content.html", context)
    return templates.TemplateResponse("dashboards/advisory_pipeline.html", context)


# ---------------------------------------------------------------------------
# ADVISORY PIPELINE — Chart & Drill-down HTMX partials
# ---------------------------------------------------------------------------

@router.get("/advisory-pipeline/chart", response_class=HTMLResponse)
async def advisory_pipeline_chart(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    group_by: str = Query("stage"),
    service: str = Query(""),
    asset_class: str = Query("", alias="asset_class"),
    owner: str = Query(""),
    org_type: str = Query("", alias="org_type"),
    date_from: str = Query("", alias="from"),
    date_to: str = Query("", alias="to"),
    active_filter: str = Query("active", alias="active_filter"),
    stage: str = Query("", alias="stage"),
):
    """HTMX partial: advisory pipeline chart grouped by selected dimension."""
    all_leads = _load_advisory_leads(service, asset_class, owner, org_type, date_from, date_to, active_filter, stage)
    bars = _group_advisory_leads(all_leads, group_by)

    context = {
        "request": request,
        "pipeline_by_stage": bars,
        "group_by": group_by,
        # Pass filter params for drill-down links
        "filter_service": service,
        "filter_asset_class": asset_class,
        "filter_owner": owner,
        "filter_org_type": org_type,
        "filter_date_from": date_from,
        "filter_date_to": date_to,
        "filter_active": active_filter,
        "filter_stage": stage,
    }
    return templates.TemplateResponse("dashboards/_advisory_chart.html", context)


@router.get("/advisory-pipeline/drilldown", response_class=HTMLResponse)
async def advisory_pipeline_drilldown(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    dimension: str = Query("stage"),
    value: str = Query(""),
    service: str = Query(""),
    asset_class: str = Query("", alias="asset_class"),
    owner: str = Query(""),
    org_type: str = Query("", alias="org_type"),
    date_from: str = Query("", alias="from"),
    date_to: str = Query("", alias="to"),
    active_filter: str = Query("active", alias="active_filter"),
    stage: str = Query("", alias="stage"),
):
    """HTMX partial: drill-down table for a specific bar in advisory chart."""
    # Build extra_filters from dashboard context
    extra_filters = {"lead_type": "advisory"}

    # Pre-load leads matching dashboard filters to get IDs
    all_leads = _load_advisory_leads(service, asset_class, owner, org_type, date_from, date_to, active_filter, stage)

    # Filter to matching dimension+value
    matching_leads = []
    for lead in all_leads:
        if dimension == "stage" and str(lead.get("rating", "")) == value:
            matching_leads.append(lead)
        elif dimension == "service_type" and str(lead.get("service_type", "")) == value:
            matching_leads.append(lead)
        elif dimension == "owner" and str(lead.get("aksia_owner_id", "")) == value:
            matching_leads.append(lead)
        elif dimension == "fund" and str(lead.get("fund_id", "")) == value:
            matching_leads.append(lead)
        elif dimension == "asset_class":
            ac_list = lead.get("asset_classes") or []
            if value in ac_list:
                matching_leads.append(lead)
        elif dimension not in ("stage", "service_type", "owner", "fund", "asset_class"):
            # Generic field grouping
            fval = lead.get(dimension)
            if isinstance(fval, list):
                if value in fval:
                    matching_leads.append(lead)
            elif str(fval or "") == value:
                matching_leads.append(lead)

    lead_ids = [str(l["id"]) for l in matching_leads]
    extra_filters["_lead_ids"] = lead_ids if lead_ids else ["00000000-0000-0000-0000-000000000000"]

    # Build drilldown base URL for HTMX reloads (preserves all dashboard context)
    drilldown_params = f"dimension={dimension}&value={value}&service={service}&asset_class={asset_class}&owner={owner}&org_type={org_type}&from={date_from}&to={date_to}&active_filter={active_filter}&stage={stage}"
    drilldown_base_url = f"/dashboards/advisory-pipeline/drilldown?{drilldown_params}"

    from services.grid_service import build_grid_context
    grid_ctx = build_grid_context(
        entity_type="lead",
        request=request,
        user=current_user,
        base_url=drilldown_base_url,
        extra_filters=extra_filters,
        grid_container_id_override="drilldown-lead-grid-container",
    )

    # Build dimension label for display
    dim_labels = {
        "stage": "Stage", "service_type": "Service Type", "asset_class": "Asset Class",
        "owner": "Owner", "fund": "Fund",
    }
    # Add dynamic field labels from groupable fields
    for gf in _get_groupable_fields("lead"):
        if gf["value"] not in dim_labels:
            dim_labels[gf["value"]] = gf["label"]

    # Add drilldown metadata
    grid_ctx["drilldown_dimension"] = dim_labels.get(dimension, dimension.replace("_", " ").title())
    grid_ctx["drilldown_value"] = value.replace("_", " ").title()
    grid_ctx["is_drilldown"] = True
    grid_ctx["hide_column_filters"] = True
    grid_ctx["request"] = request
    grid_ctx["user"] = current_user

    return templates.TemplateResponse("dashboards/_advisory_drilldown.html", grid_ctx)


# ---------------------------------------------------------------------------
# CAPITAL RAISE — shared data loader & helpers
# ---------------------------------------------------------------------------

def _load_capital_raise_prospects(fund_ticker: Optional[str] = None) -> tuple[list[dict], list[dict], dict, Optional[dict]]:
    """Load capital raise prospects. Returns (prospects, funds, funds_by_id, current_fund)."""
    sb = get_supabase()
    funds_resp = sb.table("funds").select("id, fund_name, ticker, brand, target_raise_mn").eq("is_active", True).order("ticker").execute()
    funds = funds_resp.data or []
    funds_by_ticker = {f["ticker"]: f for f in funds}
    funds_by_id = {str(f["id"]): f for f in funds}

    current_fund = None
    if fund_ticker and fund_ticker in funds_by_ticker:
        current_fund = funds_by_ticker[fund_ticker]

    query = (
        sb.table("leads")
        .select("id, organization_id, fund_id, rating, target_allocation_mn, "
                "soft_circle_mn, hard_circle_mn, probability_pct, share_class, "
                "decline_reason, aksia_owner_id, lead_type, summary")
        .eq("is_deleted", False)
        .in_("lead_type", ["fundraise", "product"])
    )
    if current_fund:
        query = query.eq("fund_id", str(current_fund["id"]))

    resp = query.execute()
    prospects = resp.data or []
    for fp in prospects:
        fp["stage"] = fp.get("rating", "target_identified")

    return prospects, funds, funds_by_id, current_fund


def _build_capital_raise_funnel(prospects: list[dict]) -> list[dict]:
    """Build vertical funnel stages for capital raise pipeline."""
    total = len(prospects)
    if total == 0:
        return []
    # Funnel: Total -> Active (excl declined) -> Due Diligence+ -> Soft Circle+ -> Closed
    active = [fp for fp in prospects if fp.get("stage") != "declined"]
    dd_plus_stages = {"due_diligence", "ic_review", "soft_circle", "legal_docs", "closed"}
    dd_plus = [fp for fp in prospects if fp.get("stage") in dd_plus_stages]
    sc_plus_stages = {"soft_circle", "legal_docs", "closed"}
    sc_plus = [fp for fp in prospects if fp.get("stage") in sc_plus_stages]
    closed = [fp for fp in prospects if fp.get("stage") == "closed"]
    return [
        {"label": "Total Prospects", "count": total, "pct": 100.0, "bg_class": "bg-blue-500"},
        {"label": "Active", "count": len(active), "pct": _pct(len(active), total), "bg_class": "bg-indigo-500"},
        {"label": "Due Diligence+", "count": len(dd_plus), "pct": _pct(len(dd_plus), total), "bg_class": "bg-yellow-500"},
        {"label": "Soft Circle+", "count": len(sc_plus), "pct": _pct(len(sc_plus), total), "bg_class": "bg-purple-500"},
        {"label": "Closed", "count": len(closed), "pct": _pct(len(closed), total), "bg_class": "bg-green-500"},
    ]


def _group_capital_raise_prospects(prospects: list[dict], group_by: str) -> list[dict]:
    """Group capital raise prospects by a dimension, returning bar chart data."""
    all_stages = get_reference_data("lead_stage")
    fundraise_stages = [s for s in all_stages if s.get("parent_value") == "fundraise"]
    stage_labels = {s["value"]: s["label"] for s in fundraise_stages}
    org_type_labels = {o["value"]: o["label"] for o in get_reference_data("organization_type")}

    groups: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_allocation": 0.0})

    color_cycle = ["bg-blue-400", "bg-indigo-400", "bg-purple-400", "bg-cyan-400",
                   "bg-teal-400", "bg-yellow-400", "bg-orange-400", "bg-pink-400",
                   "bg-green-400", "bg-red-400", "bg-gray-400"]

    # Resolve org data if needed for lp_type grouping
    org_map = {}
    if group_by == "lp_type":
        org_ids = list({str(fp["organization_id"]) for fp in prospects if fp.get("organization_id")})
        org_map = batch_resolve_orgs(org_ids)

    for fp in prospects:
        if group_by == "stage":
            key = fp.get("stage", "target_identified")
        elif group_by == "lp_type":
            org_data = org_map.get(str(fp.get("organization_id", "")), {})
            key = org_data.get("organization_type", "unknown") if isinstance(org_data, dict) else "unknown"
        elif group_by == "fund":
            key = str(fp.get("fund_id") or "none")
        else:
            key = fp.get("stage", "target_identified")
        groups[key]["count"] += 1
        groups[key]["total_allocation"] += _safe_float(fp.get("target_allocation_mn"))

    # Resolve labels & ordering
    if group_by == "stage":
        label_map = stage_labels
        ordered_keys = [s for s in FP_STAGE_ORDER if s in groups]
        color_map = FP_STAGE_COLORS
    elif group_by == "lp_type":
        label_map = org_type_labels
        ordered_keys = sorted(groups.keys(), key=lambda k: groups[k]["total_allocation"], reverse=True)
        color_map = {}
    elif group_by == "fund":
        sb = get_supabase()
        fund_ids = [k for k in groups.keys() if k != "none"]
        fund_names: dict[str, str] = {}
        if fund_ids:
            fr = sb.table("funds").select("id, ticker, fund_name").in_("id", fund_ids).execute()
            fund_names = {str(f["id"]): f.get("ticker") or f.get("fund_name", "?") for f in (fr.data or [])}
        label_map = {k: fund_names.get(k, "Unknown Fund") for k in fund_ids}
        label_map["none"] = "No Fund"
        ordered_keys = sorted(groups.keys(), key=lambda k: groups[k]["total_allocation"], reverse=True)
        color_map = {}
    else:
        label_map = stage_labels
        ordered_keys = sorted(groups.keys())
        color_map = FP_STAGE_COLORS

    max_alloc = max((g["total_allocation"] for g in groups.values()), default=1) or 1

    bars = []
    for idx, key in enumerate(ordered_keys):
        g = groups[key]
        if g["count"] == 0:
            continue
        bars.append({
            "key": key,
            "label": label_map.get(key, key.replace("_", " ").title()),
            "count": g["count"],
            "total_allocation": g["total_allocation"],
            "allocation_fmt": _fmt_mn(g["total_allocation"]),
            "bar_pct": _pct(g["total_allocation"], max_alloc),
            "color": color_map.get(key, color_cycle[idx % len(color_cycle)]),
        })
    return bars


# ---------------------------------------------------------------------------
# CAPITAL RAISE DASHBOARD
# ---------------------------------------------------------------------------

@router.get("/capital-raise", response_class=HTMLResponse)
async def capital_raise_all(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Capital Raise Dashboard — all funds."""
    return await _render_capital_raise(request, current_user, fund_ticker=None)


# Static paths must come before {fund_ticker} dynamic path
@router.get("/capital-raise/chart", response_class=HTMLResponse)
async def capital_raise_chart(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    group_by: str = Query("stage"),
    fund_ticker: str = Query("", alias="fund_ticker"),
):
    """HTMX partial: capital raise chart grouped by selected dimension."""
    prospects, funds, funds_by_id, current_fund = _load_capital_raise_prospects(
        fund_ticker if fund_ticker else None
    )
    bars = _group_capital_raise_prospects(prospects, group_by)

    context = {
        "request": request,
        "fp_pipeline": bars,
        "cr_group_by": group_by,
        "current_fund_ticker": fund_ticker or "",
    }
    return templates.TemplateResponse("dashboards/_capital_raise_chart.html", context)


@router.get("/capital-raise/drilldown", response_class=HTMLResponse)
async def capital_raise_drilldown(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    dimension: str = Query("stage"),
    value: str = Query(""),
    fund_ticker: str = Query("", alias="fund_ticker"),
):
    """HTMX partial: drill-down table for a specific bar in capital raise chart."""
    # Build extra_filters from dashboard context
    extra_filters = {"lead_type": "fundraise"}

    # Pre-load prospects matching dashboard filters to get IDs
    prospects, funds, funds_by_id, current_fund = _load_capital_raise_prospects(
        fund_ticker if fund_ticker else None
    )

    # Filter to matching prospects based on dimension+value
    matching_prospects = []
    if dimension == "stage":
        matching_prospects = [fp for fp in prospects if fp.get("stage", "target_identified") == value]
    elif dimension == "lp_type":
        org_ids = list({str(fp["organization_id"]) for fp in prospects if fp.get("organization_id")})
        org_map = batch_resolve_orgs(org_ids)
        for fp in prospects:
            org_data = org_map.get(str(fp.get("organization_id", "")), {})
            ot = org_data.get("organization_type", "unknown") if isinstance(org_data, dict) else "unknown"
            if ot == value:
                matching_prospects.append(fp)
    elif dimension == "fund":
        matching_prospects = [fp for fp in prospects if str(fp.get("fund_id") or "none") == value]
    else:
        matching_prospects = prospects

    lead_ids = [str(fp["id"]) for fp in matching_prospects]
    extra_filters["_lead_ids"] = lead_ids if lead_ids else ["00000000-0000-0000-0000-000000000000"]

    # Build drilldown base URL for HTMX reloads (preserves all dashboard context)
    drilldown_params = f"dimension={dimension}&value={value}&fund_ticker={fund_ticker}"
    drilldown_base_url = f"/dashboards/capital-raise/drilldown?{drilldown_params}"

    from services.grid_service import build_grid_context
    grid_ctx = build_grid_context(
        entity_type="lead",
        request=request,
        user=current_user,
        base_url=drilldown_base_url,
        extra_filters=extra_filters,
        grid_container_id_override="drilldown-fundraise-grid-container",
    )

    # Add drilldown metadata
    dim_labels = {"stage": "Stage", "lp_type": "LP Type", "fund": "Fund"}
    grid_ctx["drilldown_dimension"] = dim_labels.get(dimension, dimension.replace("_", " ").title())
    grid_ctx["drilldown_value"] = value.replace("_", " ").title()
    grid_ctx["is_drilldown"] = True
    grid_ctx["hide_column_filters"] = True
    grid_ctx["request"] = request
    grid_ctx["user"] = current_user

    return templates.TemplateResponse("dashboards/_capital_raise_drilldown.html", grid_ctx)


@router.get("/capital-raise/{fund_ticker}", response_class=HTMLResponse)
async def capital_raise_fund(
    request: Request,
    fund_ticker: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Capital Raise Dashboard — specific fund."""
    return await _render_capital_raise(request, current_user, fund_ticker=fund_ticker)


async def _render_capital_raise(request: Request, current_user: CurrentUser, fund_ticker: Optional[str]):
    """Shared renderer for capital raise dashboard."""
    prospects, funds, funds_by_id, current_fund = _load_capital_raise_prospects(fund_ticker)

    # Batch resolve orgs
    org_ids = list({str(fp["organization_id"]) for fp in prospects if fp.get("organization_id")})
    org_map = batch_resolve_orgs(org_ids)

    # Reference data
    all_stages = get_reference_data("lead_stage")
    fundraise_stages = [s for s in all_stages if s.get("parent_value") == "fundraise"]
    stage_labels = {s["value"]: s["label"] for s in fundraise_stages}
    decline_labels = {d["value"]: d["label"] for d in get_reference_data("decline_reason")}
    org_type_labels = {o["value"]: o["label"] for o in get_reference_data("organization_type")}

    # --- Aggregations ---
    active_prospects = [fp for fp in prospects if fp.get("stage") != "declined"]

    total_target = sum(_safe_float(fp.get("target_allocation_mn")) for fp in active_prospects)
    total_soft = sum(_safe_float(fp.get("soft_circle_mn")) for fp in active_prospects)
    total_hard = sum(_safe_float(fp.get("hard_circle_mn")) for fp in active_prospects)

    # Pace-to-target
    fund_target = _safe_float(current_fund.get("target_raise_mn")) if current_fund else None
    if fund_target and fund_target > 0:
        target_pct = min(100, _pct(total_target, fund_target))
        soft_pct = min(100, _pct(total_soft, fund_target))
        hard_pct = min(100, _pct(total_hard, fund_target))
        pace_pct = hard_pct
        if pace_pct >= 75:
            pace_label, pace_bg, pace_text = "On Track", "bg-green-50 border-green-200", "text-green-700"
        elif pace_pct >= 50:
            pace_label, pace_bg, pace_text = "Moderate", "bg-yellow-50 border-yellow-200", "text-yellow-700"
        else:
            pace_label, pace_bg, pace_text = "Behind", "bg-red-50 border-red-200", "text-red-700"
    else:
        target_pct = 100 if total_target > 0 else 0
        soft_pct = _pct(total_soft, total_target) if total_target > 0 else 0
        hard_pct = _pct(total_hard, total_target) if total_target > 0 else 0
        fund_target = None
        pace_pct = 0
        pace_label, pace_bg, pace_text = "", "", ""

    # Pipeline by Stage (default group-by)
    fp_pipeline = _group_capital_raise_prospects(prospects, "stage")

    # Funnel (vertical)
    funnel_stages = _build_capital_raise_funnel(prospects)

    # Investor Breakdown by Org Type
    investor_groups = defaultdict(lambda: {"count": 0, "target": 0.0, "soft": 0.0, "hard": 0.0})
    for fp in active_prospects:
        org_data = org_map.get(str(fp.get("organization_id", "")), {})
        org_type_val = org_data.get("organization_type", "unknown") if isinstance(org_data, dict) else "unknown"
        investor_groups[org_type_val]["count"] += 1
        investor_groups[org_type_val]["target"] += _safe_float(fp.get("target_allocation_mn"))
        investor_groups[org_type_val]["soft"] += _safe_float(fp.get("soft_circle_mn"))
        investor_groups[org_type_val]["hard"] += _safe_float(fp.get("hard_circle_mn"))

    investor_breakdown = [
        {
            "org_type": k,
            "label": org_type_labels.get(k, k.replace("_", " ").title()),
            "count": v["count"],
            "target_fmt": _fmt_mn(v["target"]),
            "soft_fmt": _fmt_mn(v["soft"]),
            "hard_fmt": _fmt_mn(v["hard"]),
        }
        for k, v in sorted(investor_groups.items(), key=lambda x: x[1]["target"], reverse=True)
    ]

    # Declined Prospects
    declined = []
    for fp in prospects:
        if fp.get("stage") != "declined":
            continue
        org_data = org_map.get(str(fp.get("organization_id", "")), {})
        org_name = org_data.get("company_name", "Unknown") if isinstance(org_data, dict) else "Unknown"
        fund_data = funds_by_id.get(str(fp.get("fund_id", "")), {})
        declined.append({
            "org_name": org_name,
            "fund_ticker": fund_data.get("ticker", "?"),
            "share_class": (fp.get("share_class") or "").replace("_", " ").title(),
            "decline_reason": decline_labels.get(fp.get("decline_reason", ""), fp.get("decline_reason", "—")),
        })

    last_refreshed = datetime.now().strftime("%b %d, %Y %I:%M %p")

    context = {
        "request": request,
        "user": current_user,
        "funds": funds,
        "current_fund_ticker": fund_ticker,
        "current_fund": current_fund,
        "last_refreshed": last_refreshed,
        # Allocation
        "total_target": total_target,
        "total_target_fmt": _fmt_mn(total_target),
        "total_soft": total_soft,
        "total_soft_fmt": _fmt_mn(total_soft),
        "total_hard": total_hard,
        "total_hard_fmt": _fmt_mn(total_hard),
        "fund_target": fund_target,
        "fund_target_fmt": _fmt_mn(fund_target) if fund_target else None,
        "target_pct": target_pct,
        "soft_pct": soft_pct,
        "hard_pct": hard_pct,
        "pace_pct": pace_pct,
        "pace_label": pace_label,
        "pace_bg": pace_bg,
        "pace_text": pace_text,
        # Pipeline (default group-by)
        "fp_pipeline": fp_pipeline,
        "cr_group_by": "stage",
        # Funnel (vertical)
        "funnel_stages": funnel_stages,
        # Investors
        "investor_breakdown": investor_breakdown,
        # Declined
        "declined": declined,
        "total_prospects": len(prospects),
    }

    return templates.TemplateResponse("dashboards/capital_raise.html", context)


# ---------------------------------------------------------------------------
# MANAGEMENT DASHBOARD — GET /dashboards/management
# ---------------------------------------------------------------------------

@router.get("/management", response_class=HTMLResponse)
async def management_dashboard(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Management Dashboard — admin-only high-level KPIs."""
    require_role(current_user, ["admin"])

    sb = get_supabase()

    # --- Load data ---
    leads_resp = (
        sb.table("leads")
        .select("id, rating, service_type, asset_classes, expected_revenue, "
                "expected_yr1_flar, expected_longterm_flar, aksia_owner_id, created_at, lead_type")
        .eq("is_deleted", False)
        .execute()
    )
    all_leads = leads_resp.data or []

    contracts_resp = (
        sb.table("contracts")
        .select("id, actual_revenue")
        .eq("is_deleted", False)
        .execute()
    )
    all_contracts = contracts_resp.data or []

    # Fundraise/product leads (replaces fund_prospects query)
    fp_resp = (
        sb.table("leads")
        .select("id, fund_id, rating, target_allocation_mn, hard_circle_mn, created_at, lead_type")
        .eq("is_deleted", False)
        .in_("lead_type", ["fundraise", "product"])
        .execute()
    )
    all_fps = fp_resp.data or []
    # Normalize stage field name
    for fp in all_fps:
        fp["stage"] = fp.get("rating", "target_identified")

    activities_resp = (
        sb.table("activities")
        .select("id, author_id, effective_date")
        .eq("is_deleted", False)
        .execute()
    )
    all_activities = activities_resp.data or []

    people_resp = (
        sb.table("people")
        .select("id, email, phone")
        .eq("is_deleted", False)
        .execute()
    )
    all_people = people_resp.data or []

    funds_resp = sb.table("funds").select("id, ticker, target_raise_mn").eq("is_active", True).order("ticker").execute()
    funds = funds_resp.data or []
    funds_by_id = {str(f["id"]): f for f in funds}

    # Load all users for name resolution
    users_resp = sb.table("users").select("id, display_name").eq("is_active", True).execute()
    all_users = {str(u["id"]): u["display_name"] for u in (users_resp.data or [])}

    # --- 1. Firm-Wide KPI Cards ---
    # Filter to advisory leads only for pipeline revenue/FLAR
    advisory_leads = [l for l in all_leads if l.get("lead_type", "advisory") == "advisory"]
    active_leads = [l for l in advisory_leads if l.get("rating") not in LEAD_INACTIVE_STAGES]
    advisory_pipeline_rev = sum(_safe_float(l.get("expected_revenue")) for l in active_leads)
    active_fps = [fp for fp in all_fps if fp.get("stage") != "declined"]
    fundraising_pipeline = sum(_safe_float(fp.get("target_allocation_mn")) for fp in active_fps)
    total_flar = sum(_safe_float(l.get("expected_yr1_flar")) + _safe_float(l.get("expected_longterm_flar")) for l in active_leads)
    contracts_revenue = sum(_safe_float(c.get("actual_revenue")) for c in all_contracts)

    # --- 2. Per-Fund Progress ---
    fund_hard_circles = defaultdict(float)
    for fp in active_fps:
        fid = str(fp.get("fund_id", ""))
        fund_hard_circles[fid] += _safe_float(fp.get("hard_circle_mn"))

    fund_progress = []
    for fund in funds:
        fid = str(fund["id"])
        hard = fund_hard_circles.get(fid, 0.0)
        target = _safe_float(fund.get("target_raise_mn"))
        pct = _pct(hard, target) if target > 0 else 0
        if pct >= 75:
            bar_color = "bg-green-400"
        elif pct >= 50:
            bar_color = "bg-yellow-400"
        else:
            bar_color = "bg-red-400"
        fund_progress.append({
            "ticker": fund["ticker"],
            "hard_circle": _fmt_mn(hard),
            "target": _fmt_mn(target) if target > 0 else "N/A",
            "pct": min(pct, 100),
            "bar_color": bar_color,
        })

    # --- 3. Quarter-over-Quarter ---
    today = date_type.today()
    q_month = ((today.month - 1) // 3) * 3 + 1
    current_q_start = today.replace(month=q_month, day=1)
    if q_month == 1:
        prev_q_start = date_type(today.year - 1, 10, 1)
    else:
        prev_q_start = date_type(today.year, q_month - 3, 1)
    prev_q_end = current_q_start - timedelta(days=1)

    def _in_range(created_at: str, start: date_type, end: Optional[date_type] = None) -> bool:
        try:
            d = str(created_at)[:10]
            if end:
                return str(start) <= d <= str(end)
            return d >= str(start)
        except (ValueError, TypeError):
            return False

    cur_q_leads = [l for l in all_leads if _in_range(l.get("created_at", ""), current_q_start)]
    prev_q_leads = [l for l in all_leads if _in_range(l.get("created_at", ""), prev_q_start, prev_q_end)]
    cur_q_fps = [fp for fp in all_fps if _in_range(fp.get("created_at", ""), current_q_start)]
    prev_q_fps = [fp for fp in all_fps if _in_range(fp.get("created_at", ""), prev_q_start, prev_q_end)]

    cur_q_rev = sum(_safe_float(l.get("expected_revenue")) for l in cur_q_leads)
    prev_q_rev = sum(_safe_float(l.get("expected_revenue")) for l in prev_q_leads)

    qoq = {
        "cur_leads": len(cur_q_leads),
        "prev_leads": len(prev_q_leads),
        "leads_delta": len(cur_q_leads) - len(prev_q_leads),
        "cur_revenue": _fmt_currency(cur_q_rev),
        "prev_revenue": _fmt_currency(prev_q_rev),
        "revenue_delta": cur_q_rev - prev_q_rev,
        "revenue_delta_fmt": _fmt_currency(abs(cur_q_rev - prev_q_rev)),
        "cur_fps": len(cur_q_fps),
        "prev_fps": len(prev_q_fps),
        "fps_delta": len(cur_q_fps) - len(prev_q_fps),
    }

    # --- 4. Team Activity ---
    thirty_days_ago = today - timedelta(days=30)
    recent_activities = [a for a in all_activities if _in_range(a.get("effective_date", ""), thirty_days_ago)]

    act_by_user = defaultdict(int)
    for a in recent_activities:
        uid = str(a.get("author_id", ""))
        if uid:
            act_by_user[uid] += 1

    leads_by_owner = defaultdict(lambda: {"active": 0, "pipeline_revenue": 0.0})
    for l in active_leads:
        oid = str(l.get("aksia_owner_id", ""))
        if oid:
            leads_by_owner[oid]["active"] += 1
            leads_by_owner[oid]["pipeline_revenue"] += _safe_float(l.get("expected_revenue"))

    all_user_ids = set(act_by_user.keys()) | set(leads_by_owner.keys())
    team_activity = []
    for uid in all_user_ids:
        team_activity.append({
            "name": all_users.get(uid, "Unknown"),
            "activities_30d": act_by_user.get(uid, 0),
            "active_leads": leads_by_owner.get(uid, {}).get("active", 0),
            "pipeline_revenue": _fmt_currency(leads_by_owner.get(uid, {}).get("pipeline_revenue", 0.0)),
        })
    team_activity.sort(key=lambda x: x["activities_30d"], reverse=True)

    # --- 5. Data Quality ---
    leads_missing = 0
    for l in active_leads:
        if not l.get("service_type") or not l.get("asset_classes") or not l.get("aksia_owner_id"):
            leads_missing += 1

    contacts_missing = sum(
        1 for p in all_people
        if not p.get("email") or not p.get("phone")
    )

    last_refreshed = datetime.now().strftime("%b %d, %Y %I:%M %p")

    context = {
        "request": request,
        "user": current_user,
        "last_refreshed": last_refreshed,
        # KPIs
        "advisory_pipeline_rev": _fmt_currency(advisory_pipeline_rev),
        "fundraising_pipeline": _fmt_mn(fundraising_pipeline),
        "total_flar": _fmt_currency(total_flar),
        "contracts_revenue": _fmt_currency(contracts_revenue),
        # Fund progress
        "fund_progress": fund_progress,
        # QoQ
        "qoq": qoq,
        # Team
        "team_activity": team_activity,
        # Data quality
        "leads_missing": leads_missing,
        "contacts_missing": contacts_missing,
    }

    return templates.TemplateResponse("dashboards/management.html", context)

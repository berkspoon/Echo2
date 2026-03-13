"""Echo 2.0 — FastAPI application entry point."""

from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config import get_settings
from dependencies import CurrentUser, get_current_user
from routers import (
    organizations,
    people,
    activities,
    leads,
    contracts,
    fund_prospects,
    distribution_lists,
    tasks,
    dashboards,
    admin,
)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

# ---------------------------------------------------------------------------
# Static files & templates
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(organizations.router)
app.include_router(people.router)
app.include_router(activities.router)
app.include_router(leads.router)
app.include_router(contracts.router)
app.include_router(fund_prospects.router)
app.include_router(distribution_lists.router)
app.include_router(tasks.router)
app.include_router(dashboards.router)
app.include_router(admin.router)

# ---------------------------------------------------------------------------
# Root / Homepage
# ---------------------------------------------------------------------------

@app.get("/")
async def homepage(request: Request, current_user: CurrentUser = Depends(get_current_user)):
    """Personal dashboard — landing page after login."""
    return templates.TemplateResponse("index.html", {"request": request, "user": current_user})

"""Echo 2.0 — FastAPI application entry point."""

import secrets
from base64 import b64decode

from fastapi import Depends, FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from config import get_settings
from dependencies import CurrentUser, get_current_user
from routers import (
    organizations,
    people,
    activities,
    leads,
    contracts,
    distribution_lists,
    tasks,
    dashboards,
    admin,
    documents,
    views,
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

class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Gate the whole app behind a single shared password (HTTP Basic Auth).

    Enabled only when TESTER_PASSWORD is set. Intended as a simple tester
    gate until real SSO is wired up. Any username is accepted.
    """

    def __init__(self, app, password: str):
        super().__init__(app)
        self.password = password

    async def dispatch(self, request: Request, call_next):
        header = request.headers.get("authorization", "")
        if header.startswith("Basic "):
            try:
                decoded = b64decode(header[6:]).decode("utf-8")
                _, _, supplied = decoded.partition(":")
                if secrets.compare_digest(supplied, self.password):
                    return await call_next(request)
            except Exception:
                pass
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Echo 2.0 Tester Access"'},
            content="Authentication required.",
        )


if settings.tester_password:
    app.add_middleware(BasicAuthMiddleware, password=settings.tester_password)

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
app.include_router(distribution_lists.router)
app.include_router(tasks.router)
app.include_router(dashboards.router)
app.include_router(admin.router)
app.include_router(documents.router)
app.include_router(views.router)

# ---------------------------------------------------------------------------
# Root / Homepage
# ---------------------------------------------------------------------------

@app.get("/")
async def homepage(request: Request, current_user: CurrentUser = Depends(get_current_user)):
    """Personal dashboard — landing page after login."""
    return templates.TemplateResponse("index.html", {"request": request, "user": current_user})

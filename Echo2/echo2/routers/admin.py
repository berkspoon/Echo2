"""Admin router — stub."""

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")

# TODO: Admin dashboard
# TODO: List users
# TODO: Create user
# TODO: Update user
# TODO: Deactivate user
# TODO: Manage roles and permissions
# TODO: System settings
# TODO: Audit log

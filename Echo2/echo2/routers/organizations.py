"""Organizations router — stub."""

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/organizations", tags=["organizations"])
templates = Jinja2Templates(directory="templates")

# TODO: List organizations
# TODO: Get organization detail
# TODO: Create organization form
# TODO: Create organization
# TODO: Update organization
# TODO: Delete organization
# TODO: Search organizations

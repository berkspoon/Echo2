"""Distribution lists router — stub."""

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/distribution-lists", tags=["distribution_lists"])
templates = Jinja2Templates(directory="templates")

# TODO: List distribution lists
# TODO: Get distribution list detail
# TODO: Create distribution list form
# TODO: Create distribution list
# TODO: Update distribution list
# TODO: Delete distribution list
# TODO: Add members to distribution list
# TODO: Remove members from distribution list
# TODO: Export distribution list

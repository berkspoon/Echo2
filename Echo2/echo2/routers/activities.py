"""Activities router — stub."""

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/activities", tags=["activities"])
templates = Jinja2Templates(directory="templates")

# TODO: List activities
# TODO: Get activity detail
# TODO: Create activity form
# TODO: Create activity
# TODO: Update activity
# TODO: Delete activity
# TODO: Filter activities by type (call, email, meeting, note)

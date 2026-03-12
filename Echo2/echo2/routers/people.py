"""People router — stub."""

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/people", tags=["people"])
templates = Jinja2Templates(directory="templates")

# TODO: List people
# TODO: Get person detail
# TODO: Create person form
# TODO: Create person
# TODO: Update person
# TODO: Delete person
# TODO: Search people
# TODO: List person activities

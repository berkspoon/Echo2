"""Fund prospects router — stub."""

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/fund-prospects", tags=["fund_prospects"])
templates = Jinja2Templates(directory="templates")

# TODO: List fund prospects
# TODO: Get fund prospect detail
# TODO: Create fund prospect form
# TODO: Create fund prospect
# TODO: Update fund prospect
# TODO: Delete fund prospect
# TODO: Update fund prospect stage
# TODO: Link fund prospect to organization

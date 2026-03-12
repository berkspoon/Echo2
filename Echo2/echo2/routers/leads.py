"""Leads router — stub."""

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/leads", tags=["leads"])
templates = Jinja2Templates(directory="templates")

# TODO: List leads
# TODO: Get lead detail
# TODO: Create lead form
# TODO: Create lead
# TODO: Update lead
# TODO: Delete lead
# TODO: Convert lead to opportunity
# TODO: Update lead status

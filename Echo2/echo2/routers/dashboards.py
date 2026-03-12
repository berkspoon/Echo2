"""Dashboards router — stub."""

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/dashboards", tags=["dashboards"])
templates = Jinja2Templates(directory="templates")

# TODO: Main dashboard view
# TODO: Pipeline overview widget
# TODO: Recent activities widget
# TODO: Tasks due widget
# TODO: Leads summary widget
# TODO: Fund prospects summary widget

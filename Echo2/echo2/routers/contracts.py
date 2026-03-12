"""Contracts router — stub."""

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/contracts", tags=["contracts"])
templates = Jinja2Templates(directory="templates")

# TODO: List contracts
# TODO: Get contract detail
# TODO: Create contract form
# TODO: Create contract
# TODO: Update contract
# TODO: Delete contract
# TODO: Renew contract
# TODO: Update contract status

"""Tasks router — stub."""

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/tasks", tags=["tasks"])
templates = Jinja2Templates(directory="templates")

# TODO: List tasks
# TODO: Get task detail
# TODO: Create task form
# TODO: Create task
# TODO: Update task
# TODO: Delete task
# TODO: Mark task complete
# TODO: Assign task to user
# TODO: Filter tasks by status (open, completed, overdue)

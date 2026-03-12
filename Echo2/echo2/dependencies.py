"""Shared FastAPI dependencies — auth, role checks, etc."""

from uuid import UUID
from fastapi import Depends, HTTPException, Request, status


# ---------------------------------------------------------------------------
# User model (lightweight dict-like object for dependency injection)
# ---------------------------------------------------------------------------

class CurrentUser:
    """Represents the currently authenticated user.

    Populated from the session (real SSO) or from a dev stub.
    """

    def __init__(self, *, id: UUID, email: str, display_name: str, role: str):
        self.id = id
        self.email = email
        self.display_name = display_name
        self.role = role

    @property
    def initials(self) -> str:
        parts = self.display_name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return self.display_name[:2].upper()


# ---------------------------------------------------------------------------
# Dev stub user (used until SSO is wired up)
# ---------------------------------------------------------------------------

_DEV_USER = CurrentUser(
    id=UUID("00000000-0000-0000-0000-000000000001"),
    email="dev@aksia.com",
    display_name="Dev User",
    role="admin",
)


async def get_current_user(request: Request) -> CurrentUser:
    """Return the current user from the session.

    TODO: Replace with real MSAL session lookup once SSO is implemented.
    For now, returns a dev admin user so routes can be tested.
    """
    # When SSO is live, this will read from request.session["user"]
    return _DEV_USER


# ---------------------------------------------------------------------------
# Role-based access control
# ---------------------------------------------------------------------------

def require_role(user: CurrentUser, allowed_roles: list[str]) -> None:
    """Raise 403 if user's role is not in allowed_roles."""
    if user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{user.role}' is not permitted for this action.",
        )

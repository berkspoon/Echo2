"""Shared FastAPI dependencies — auth, role checks, etc."""

from uuid import UUID
from fastapi import Depends, HTTPException, Request, status


# ---------------------------------------------------------------------------
# User model (lightweight dict-like object for dependency injection)
# ---------------------------------------------------------------------------

class CurrentUser:
    """Represents the currently authenticated user.

    Populated from the session (real SSO) or from a dev stub.
    Supports multiple roles via the `roles` list, with backward-compatible
    `role` property that returns the primary (first) role.
    """

    def __init__(
        self,
        *,
        id: UUID,
        email: str,
        display_name: str,
        role: str = "",
        roles: list[str] | None = None,
        permissions: dict | None = None,
    ):
        self.id = id
        self.email = email
        self.display_name = display_name
        # Support both old single-role and new multi-role
        if roles:
            self.roles = roles
        elif role:
            self.roles = [role]
        else:
            self.roles = ["standard_user"]
        self._permissions = permissions or {}

    @property
    def role(self) -> str:
        """Backward-compatible: return the primary (first) role."""
        return self.roles[0] if self.roles else "standard_user"

    @property
    def initials(self) -> str:
        parts = self.display_name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return self.display_name[:2].upper()

    def has_role(self, role_name: str) -> bool:
        """Check if user has a specific role."""
        return role_name in self.roles

    def has_permission(self, entity_type: str, action: str) -> bool:
        """Check if user has permission for an action on an entity type.

        Aggregates across all roles — permissions are additive.
        """
        entities = self._permissions.get("entities", {})
        # Check wildcard
        if "*" in entities and action in entities["*"]:
            return True
        # Check specific entity
        if entity_type in entities and action in entities[entity_type]:
            return True
        return False


# ---------------------------------------------------------------------------
# Dev stub user (used until SSO is wired up)
# ---------------------------------------------------------------------------

_DEV_USER = CurrentUser(
    id=UUID("00000000-0000-0000-0000-000000000001"),
    email="dev@aksia.com",
    display_name="Dev User",
    roles=["admin"],
    permissions={
        "entities": {"*": ["create", "read", "update", "delete", "archive", "restore"]},
        "admin_panel": True,
        "manage_users": True,
        "manage_roles": True,
        "manage_fields": True,
    },
)


async def get_current_user(request: Request) -> CurrentUser:
    """Return the current user from the session.

    TODO: Replace with real MSAL session lookup once SSO is implemented.
    For now, returns a dev admin user so routes can be tested.
    When SSO is live, this will:
    1. Read user info from request.session["user"]
    2. Query user_roles JOIN roles to build the roles list
    3. Aggregate permissions across all roles
    """
    # When SSO is live, this will read from request.session["user"]
    return _DEV_USER


# ---------------------------------------------------------------------------
# Role-based access control
# ---------------------------------------------------------------------------

def require_role(user: CurrentUser, allowed_roles: list[str]) -> None:
    """Raise 403 if none of the user's roles are in allowed_roles.

    Works with both single-role and multi-role users.
    """
    if not any(r in allowed_roles for r in user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your roles {user.roles} are not permitted for this action.",
        )


def require_permission(
    user: CurrentUser, entity_type: str, action: str
) -> None:
    """Raise 403 if user lacks permission for the given entity action.

    Uses the JSONB permissions aggregated across all user roles.
    """
    if not user.has_permission(entity_type, action):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have '{action}' permission on '{entity_type}'.",
        )

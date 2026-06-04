"""Admin authorization — re-exports from admin_deps for convenience."""

from app.admin_deps import require_admin_user, require_permission
from app.deps import is_admin_user, require_admin

__all__ = [
    "is_admin_user",
    "require_admin",
    "require_admin_user",
    "require_permission",
]

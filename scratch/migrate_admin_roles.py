"""One-off: set super_admin from ADMIN_EMAILS for users without adminRole."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import connect_db, close_db, get_db
from app.services.admin_rbac import bootstrap_admin_roles


async def main() -> None:
    await connect_db()
    await bootstrap_admin_roles(get_db())
    await close_db()
    print("Admin roles bootstrapped.")


if __name__ == "__main__":
    asyncio.run(main())

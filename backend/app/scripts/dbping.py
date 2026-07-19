import asyncio

from app.core.config import get_settings
from app.services.database import database_service


async def main() -> None:
    settings = get_settings()
    db = settings.database
    print(f'Connecting to {db.host}:{db.port}/{db.database} as "{db.user}" ...')
    info = await database_service.ping()
    tables = await database_service.list_tables()
    print("Connected.")
    print(f"PostgreSQL    : {info['version']}")
    print(f"Database      : {info['database']}")
    print(f"Table count   : {info['tables']}")
    suffix = " …" if len(tables) > 30 else ""
    print(f"Tables        : {', '.join(tables[:30])}{suffix}")


if __name__ == "__main__":
    asyncio.run(main())

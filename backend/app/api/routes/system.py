from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import get_settings
from app.core.errors import ConfigurationError, DatabaseUnavailableError
from app.core.security import require_api_key
from app.models.api import DatabasePingResponse, HealthResponse, TablesResponse
from app.services.database import database_service
from app.services.schema import schema_service


router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        app=settings.app_name,
        environment=settings.app_env,
        database_configured=settings.database_configured,
        cloudflare_configured=settings.cloudflare_configured,
    )


@router.get(
    "/db/ping",
    response_model=DatabasePingResponse,
    dependencies=[Depends(require_api_key)],
)
async def db_ping() -> DatabasePingResponse:
    try:
        info = await database_service.ping()
        return DatabasePingResponse(reachable=True, **info)
    except (DatabaseUnavailableError, ConfigurationError, ValueError) as exc:
        return DatabasePingResponse(reachable=False, message=str(exc))


@router.get(
    "/db/tables",
    response_model=TablesResponse,
    dependencies=[Depends(require_api_key)],
)
async def tables() -> TablesResponse:
    try:
        names = await database_service.list_tables()
    except (DatabaseUnavailableError, ConfigurationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "DATABASE_UNAVAILABLE", "message": str(exc)},
        ) from exc
    return TablesResponse(tables=names, count=len(names))


@router.post("/schema/refresh", dependencies=[Depends(require_api_key)])
async def refresh_schema() -> dict[str, int | bool]:
    summary = await schema_service.get_summary(force=True)
    return {"refreshed": True, "characters": len(summary)}

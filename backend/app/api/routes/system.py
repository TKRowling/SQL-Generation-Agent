from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.config import get_settings
from app.core.errors import (
    AIResponseError,
    AIUnavailableError,
    ConfigurationError,
    DatabaseUnavailableError,
)
from app.core.security import require_api_key
from app.models.api import DatabasePingResponse, HealthResponse, TablesResponse
from app.services.database import database_service
from app.services.ai import ai_client
from app.services.schema import schema_service


router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        app=settings.app_name,
        environment=settings.app_env,
        database_configured=settings.database_configured,
        ai_configured=settings.ai_configured,
    )


@router.get("/ai/ping", dependencies=[Depends(require_api_key)])
async def ai_ping() -> dict[str, object]:
    """Verify the configured Ollama endpoint and model inventory."""
    try:
        return await ai_client.ping()
    except (AIUnavailableError, AIResponseError, ConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "AI_UNAVAILABLE", "message": str(exc)},
        ) from exc


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
async def tables(schema: str | None = Query(default=None)) -> TablesResponse:
    try:
        selected_schema = get_settings().resolve_schema(schema)
        names = await database_service.list_tables(selected_schema)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_SCHEMA", "message": str(exc)},
        ) from exc
    except (DatabaseUnavailableError, ConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "DATABASE_UNAVAILABLE", "message": str(exc)},
        ) from exc
    return TablesResponse(schema=selected_schema, tables=names, count=len(names))


@router.post("/schema/refresh", dependencies=[Depends(require_api_key)])
async def refresh_schema(schema: str | None = Query(default=None)) -> dict[str, int | bool | str]:
    selected_schema = get_settings().resolve_schema(schema)
    summary = await schema_service.get_summary(selected_schema, force=True)
    return {"refreshed": True, "schema": selected_schema, "characters": len(summary)}

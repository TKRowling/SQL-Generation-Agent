from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.config import get_settings
from app.core.errors import ConfigurationError, DatabaseUnavailableError
from app.core.security import require_api_key
from app.models.api import DatabasePingResponse, HealthResponse, TablesResponse
from app.services.database import database_service
from app.agents.graph import multi_agent_system
from app.services.schema import schema_service


router = APIRouter(tags=["system"])


@router.get("/agent/info", dependencies=[Depends(require_api_key)])
async def agent_info() -> dict[str, object]:
    """Expose the deployed graph and governed tool inventory for operations."""
    nodes = sorted(
        name
        for name in multi_agent_system.graph.get_graph().nodes
        if not name.startswith("__")
    )
    return {
        "framework": "LangGraph",
        "architecture": "bounded_multi_agent",
        "nodes": nodes,
        "tools": [
            "search_approved_schema",
            "get_schema_fingerprint",
            "validate_select_sql",
            "explain_query_cost",
            "execute_readonly_sql",
            "verify_query_result",
        ],
        "model_roles": {
            "sql": "planning_and_correction",
            "knowledge": "metadata_summary_chat_and_chart_planning",
        },
        "security_owner": "deterministic_backend_tools",
    }


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        app=settings.app_name,
        environment=settings.app_env,
        database_configured=settings.database_configured,
        ai_configured=settings.ai_configured,
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

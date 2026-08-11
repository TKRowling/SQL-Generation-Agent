import logging
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import get_settings
from app.core.errors import (
    AIResponseError,
    AIUnavailableError,
    ConfigurationError,
    DatabaseUnavailableError,
    ForbiddenQueryError,
    UnsupportedDataQuestionError,
)
from app.core.security import require_api_key
from app.models.api import (
    ChatRequest,
    ChatResponse,
    HistoryReplaceRequest,
    ResetRequest,
    ResetResponse,
)
from app.services.history import conversation_store
from app.services.audit import audit_service
from app.agents.graph import multi_agent_system
from app.services.query_agent import looks_like_destructive_request


router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(require_api_key)])
logger = logging.getLogger(__name__)


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    started = time.perf_counter()
    request_id = str(uuid4())
    settings = get_settings()
    try:
        selected_schema = settings.resolve_schema(request.schema_name)
    except ValueError as exc:
        raise api_error(status.HTTP_400_BAD_REQUEST, "INVALID_SCHEMA", str(exc)) from exc
    history = await conversation_store.get(request.session_id)

    if looks_like_destructive_request(request.message):
        response = ChatResponse(
            kind="chat",
            answer=(
                "I can only generate and execute read-only SELECT queries. "
                "I can't provide or run SQL that changes or deletes database objects or data."
            ),
            rows=[],
            row_count=0,
            sql=None,
            request_id=request_id,
        )
        await audit_service.record({"request_id": request_id, "session_id": request.session_id, "schema": selected_schema, "question": request.message, "decision": "blocked_mutation", "status": "blocked"})
        return response

    try:
        result = await multi_agent_system.run(
            question=request.message,
            schema_name=selected_schema,
            history=history,
            system_prompt=settings.bot_system_prompt,
            force_data=request.force_data,
        )
        kind = result.kind
    except ForbiddenQueryError as exc:
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "FORBIDDEN_QUERY",
            "Credential fields such as passwords or secret keys cannot be queried.",
        ) from exc
    except UnsupportedDataQuestionError as exc:
        execution_ms = round((time.perf_counter() - started) * 1000)
        await conversation_store.append_exchange(
            request.session_id, request.message, str(exc)
        )
        await audit_service.record({
            "request_id": request_id,
            "session_id": request.session_id,
            "schema": selected_schema,
            "question": request.message,
            "decision": "unsupported_by_schema",
            "status": "not_executed",
            "row_count": 0,
            "execution_ms": execution_ms,
        })
        return ChatResponse(
            kind="data",
            answer=str(exc),
            rows=[],
            row_count=0,
            sql=None,
            request_id=request_id,
            execution_ms=execution_ms,
        )
    except DatabaseUnavailableError as exc:
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DATABASE_UNAVAILABLE",
            "The PostgreSQL database is unreachable. Check that PostgreSQL is running and verify the host, port, database, user, and password.",
        ) from exc
    except AIUnavailableError as exc:
        logger.warning("AI provider request failed: %s", exc)
        message = (
            str(exc)
            if settings.app_env.lower() == "development"
            else "The configured AI provider is temporarily unavailable or rate-limited."
        )
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI_UNAVAILABLE",
            message,
        ) from exc
    except ConfigurationError as exc:
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "NOT_CONFIGURED", str(exc)) from exc
    except AIResponseError as exc:
        raise api_error(status.HTTP_502_BAD_GATEWAY, "AI_RESPONSE_ERROR", str(exc)) from exc
    except Exception as exc:
        raise api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "QUERY_FAILED",
            f"The request could not be completed: {exc}",
        ) from exc

    await conversation_store.append_exchange(request.session_id, request.message, result.answer)
    sql = result.sql if settings.expose_sql else None
    execution_ms = round((time.perf_counter() - started) * 1000)
    response = ChatResponse(
        kind=kind,
        answer=result.answer,
        rows=result.rows,
        row_count=result.row_count,
        sql=sql,
        insights=result.insights or [],
        chart=result.chart,
        request_id=request_id,
        execution_ms=execution_ms,
    )
    await audit_service.record({"request_id": request_id, "session_id": request.session_id, "schema": selected_schema, "question": request.message, "decision": kind, "status": "success", "sql": result.sql, "row_count": result.row_count, "execution_ms": execution_ms})
    return response


@router.post("/reset", response_model=ResetResponse)
async def reset_chat(request: ResetRequest) -> ResetResponse:
    await conversation_store.reset(request.session_id)
    return ResetResponse()


@router.put("/history", response_model=ResetResponse)
async def replace_history(request: HistoryReplaceRequest) -> ResetResponse:
    """Restore the valid prefix after a user edits an earlier question."""
    await conversation_store.replace(request.session_id, request.messages)
    return ResetResponse()

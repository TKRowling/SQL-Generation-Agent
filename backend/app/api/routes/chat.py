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
)
from app.core.security import require_api_key
from app.models.api import ChatRequest, ChatResponse, ResetRequest, ResetResponse
from app.services.history import conversation_store
from app.services.audit import audit_service
from app.services.query_agent import looks_like_destructive_request, query_agent
from app.services.reporting import build_report


router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(require_api_key)])


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    started = time.perf_counter()
    request_id = str(uuid4())
    settings = get_settings()
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
        await audit_service.record({"request_id": request_id, "session_id": request.session_id, "question": request.message, "decision": "blocked_mutation", "status": "blocked"})
        return response

    try:
        metadata = await query_agent.answer_metadata(request.message)
        if metadata is not None:
            result = metadata
            kind = result.kind
        elif request.force_data:
            result = await query_agent.answer_data_question(request.message, history)
            kind = "data"
        else:
            result = await query_agent.answer_message(
                request.message,
                history,
                settings.bot_system_prompt,
            )
            kind = result.kind
    except ForbiddenQueryError as exc:
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "FORBIDDEN_QUERY",
            "Credential fields such as passwords or secret keys cannot be queried.",
        ) from exc
    except DatabaseUnavailableError as exc:
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DATABASE_UNAVAILABLE",
            "The PostgreSQL database is unreachable. Check that PostgreSQL is running and verify the host, port, database, user, and password.",
        ) from exc
    except AIUnavailableError as exc:
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI_UNAVAILABLE",
            "The AI service is temporarily unavailable or rate-limited.",
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
    insights, chart = build_report(result.rows)
    execution_ms = round((time.perf_counter() - started) * 1000)
    response = ChatResponse(
        kind=kind,
        answer=result.answer,
        rows=result.rows,
        row_count=result.row_count,
        sql=sql,
        insights=insights,
        chart=chart,
        request_id=request_id,
        execution_ms=execution_ms,
    )
    await audit_service.record({"request_id": request_id, "session_id": request.session_id, "question": request.message, "decision": kind, "status": "success", "sql": result.sql, "row_count": result.row_count, "execution_ms": execution_ms})
    return response


@router.post("/reset", response_model=ResetResponse)
async def reset_chat(request: ResetRequest) -> ResetResponse:
    await conversation_store.reset(request.session_id)
    return ResetResponse()

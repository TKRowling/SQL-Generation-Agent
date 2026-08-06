from __future__ import annotations

import re
from typing import Any

from langchain_core.tools import tool

from app.core.config import get_settings
from app.core.errors import ForbiddenQueryError
from app.services.cost_guard import query_cost_guard
from app.services.database import database_service
from app.services.query_checker import query_checker
from app.services.result_verifier import verify_result
from app.services.schema import schema_service


@tool
async def search_approved_schema(
    question: str,
    schema_name: str,
    additional_terms: str = "",
    max_tables: int | None = None,
    force_refresh: bool = False,
) -> str:
    """Retrieve relevant approved table, column, key, and relationship metadata."""
    return await schema_service.get_relevant_summary(
        question,
        schema=schema_name,
        additional_terms=additional_terms,
        max_tables=max_tables,
        force=force_refresh,
    )


@tool
async def get_schema_fingerprint(schema_name: str) -> str:
    """Return a stable fingerprint of the approved schema structure."""
    return await schema_service.get_fingerprint(schema_name)


@tool
async def validate_select_sql(sql: str, schema_name: str) -> dict[str, Any]:
    """Parse SQL and authorize one SELECT against the approved schema catalog."""
    restricted = {
        name.strip().casefold()
        for name in get_settings().restricted_columns.split(",")
        if name.strip()
    }
    lowered = sql.casefold()
    if any(re.search(rf"\b{re.escape(name)}\b", lowered) for name in restricted):
        raise ForbiddenQueryError()
    checked = await query_checker.check(sql, schema_name)
    return {
        "normalized_sql": checked.normalized_sql,
        "referenced_tables": list(checked.referenced_tables),
        "projected_columns": list(checked.projected_columns),
        "join_count": checked.join_count,
    }


@tool
async def explain_query_cost(sql: str, schema_name: str) -> dict[str, Any]:
    """Run EXPLAIN without ANALYZE and enforce configured query cost limits."""
    checked = await query_cost_guard.check(sql, schema_name)
    return {
        "total_cost": checked.total_cost,
        "estimated_rows": checked.estimated_rows,
        "node_count": checked.node_count,
    }


@tool
async def execute_readonly_sql(sql: str, schema_name: str) -> list[dict[str, Any]]:
    """Execute already-approved SQL in a read-only transaction with a row cap."""
    return await database_service.run_select_in_schema(sql, schema_name)


@tool
async def verify_query_result(
    question: str,
    sql: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Verify deterministic count, top-N, ordering, limit, and chart invariants."""
    result = verify_result(question, sql, rows)
    return {"passed": result.passed, "issues": list(result.issues)}

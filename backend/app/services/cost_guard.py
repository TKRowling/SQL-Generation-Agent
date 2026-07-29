from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.services.database import database_service


@dataclass(frozen=True)
class CostCheckResult:
    total_cost: float
    estimated_rows: int
    node_count: int


def _count_plan_nodes(plan: dict[str, Any]) -> int:
    return 1 + sum(
        _count_plan_nodes(child)
        for child in plan.get("Plans", [])
        if isinstance(child, dict)
    )


def validate_explain_plan(
    payload: dict[str, Any],
    *,
    max_cost: float,
    max_rows: int,
) -> CostCheckResult:
    plan = payload.get("Plan")
    if not isinstance(plan, dict):
        raise ValueError("EXPLAIN did not return a valid plan.")
    total_cost = float(plan.get("Total Cost", 0))
    estimated_rows = int(plan.get("Plan Rows", 0))
    if total_cost > max_cost:
        raise ValueError(
            f"Estimated query cost {total_cost:,.2f} exceeds the limit {max_cost:,.2f}."
        )
    if estimated_rows > max_rows:
        raise ValueError(
            f"Estimated rows {estimated_rows:,} exceed the limit {max_rows:,}."
        )
    return CostCheckResult(
        total_cost=total_cost,
        estimated_rows=estimated_rows,
        node_count=_count_plan_nodes(plan),
    )


class QueryCostGuard:
    async def check(self, sql: str, schema: str) -> CostCheckResult:
        settings = get_settings()
        payload = await database_service.explain_select(sql, schema)
        return validate_explain_plan(
            payload,
            max_cost=settings.db_explain_max_cost,
            max_rows=settings.db_explain_max_rows,
        )


query_cost_guard = QueryCostGuard()

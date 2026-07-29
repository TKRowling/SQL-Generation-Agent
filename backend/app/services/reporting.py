from __future__ import annotations

import json
import re
from typing import Any

from app.core.errors import AIResponseError, AIUnavailableError
from app.models.api import ChartSpec, ChatMessage
from app.services.ai import workers_ai


DATE_RE = re.compile(r"date|time|month|year|week|day", re.IGNORECASE)
PIE_INTENT_RE = re.compile(
    r"\b(share|distribution|percentage|percent|proportion|breakdown|composition|mix)\b",
    re.IGNORECASE,
)
CHART_WORTHY_RE = re.compile(
    r"\b(chart|graph|visuali[sz]e|plot|trend|over time|monthly|weekly|daily|yearly|"
    r"compare|comparison|ranking|top\s+\d+|highest|lowest|distribution|breakdown|"
    r"share|percentage|percent|proportion|group(?:ed)?\s+by)\b",
    re.IGNORECASE,
)


def build_report(
    rows: list[dict[str, Any]],
    question: str = "",
) -> tuple[list[str], ChartSpec | None]:
    """Create deterministic, row-grounded insights and a chart recommendation."""
    if not rows:
        return [], None
    keys = list(rows[0])
    numeric = [key for key in keys if any(isinstance(row.get(key), (int, float)) and not isinstance(row.get(key), bool) for row in rows)]
    dimensions = [key for key in keys if key not in numeric]
    insights = [f"The query returned {len(rows)} row{'s' if len(rows) != 1 else ''}."]

    for key in numeric[:2]:
        values = [float(row[key]) for row in rows if isinstance(row.get(key), (int, float))]
        if values:
            insights.append(f"{key.replace('_', ' ').title()} ranges from {min(values):,.2f} to {max(values):,.2f}.")

    if not CHART_WORTHY_RE.search(question):
        return insights, None
    if len(rows) < 2 or not numeric or not dimensions:
        return insights, None
    x_key = next((key for key in dimensions if DATE_RE.search(key)), dimensions[0])
    chart_type = "line" if DATE_RE.search(x_key) else "bar"
    if (
        PIE_INTENT_RE.search(question)
        and not DATE_RE.search(x_key)
        and len(numeric) == 1
        and 2 <= len(rows) <= 8
    ):
        values = [row.get(numeric[0]) for row in rows]
        if all(isinstance(value, (int, float)) and value >= 0 for value in values):
            total = sum(float(value) for value in values)
            if total > 0:
                chart_type = "pie"
                largest_index = max(range(len(values)), key=lambda index: float(values[index]))
                largest_label = str(rows[largest_index].get(x_key, "Largest category"))
                largest_share = float(values[largest_index]) / total * 100
                insights.append(
                    f"{largest_label} is the largest share at {largest_share:.1f}%."
                )
    return insights, ChartSpec(
        type=chart_type,
        title=f"{numeric[0].replace('_', ' ').title()} by {x_key.replace('_', ' ').title()}",
        x_key=x_key,
        y_keys=numeric[:1] if chart_type == "pie" else numeric[:2],
    )


async def build_report_with_ai(
    rows: list[dict[str, Any]],
    question: str,
) -> tuple[list[str], ChartSpec | None]:
    """Let AI choose chart semantics, then validate the choice against exact rows."""
    insights, fallback = build_report(rows, question)
    if fallback is None:
        return insights, None

    keys = list(rows[0]) if rows else []
    numeric = [
        key for key in keys
        if any(
            isinstance(row.get(key), (int, float))
            and not isinstance(row.get(key), bool)
            for row in rows
        )
    ]
    dimensions = [key for key in keys if key not in numeric]
    payload = json.dumps(rows, ensure_ascii=False, default=str)[:6000]
    messages = [
        ChatMessage(
            role="system",
            content=(
                "You are a chart planner. The database result is authoritative. "
                "Choose a useful chart that directly answers the question; never invent, "
                "transform, aggregate, or rename data. Return JSON only with: "
                '{"type":"bar|line|pie|none","title":"short title",'
                '"x_key":"exact returned column","y_keys":["exact numeric column"]}. '
                "Use none when a chart would not improve understanding. Use line only "
                "for a requested time trend, bar for category comparison/ranking, and "
                "pie only for an explicit part-to-whole result with 2-8 categories."
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                f"Question: {question}\n"
                f"Returned columns: {keys}\nNumeric columns: {numeric}\n"
                f"Dimension columns: {dimensions}\nExact returned rows: {payload}"
            ),
        ),
    ]
    try:
        raw = (await workers_ai.chat(messages)).strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, re.IGNORECASE | re.DOTALL)
        proposal = json.loads(fenced.group(1) if fenced else raw)
        return insights, validate_chart_proposal(proposal, rows, question)
    except (AIUnavailableError, AIResponseError, ValueError, TypeError, json.JSONDecodeError):
        return insights, fallback


def validate_chart_proposal(
    proposal: Any,
    rows: list[dict[str, Any]],
    question: str,
) -> ChartSpec | None:
    if not isinstance(proposal, dict) or proposal.get("type") == "none":
        return None
    chart_type = proposal.get("type")
    x_key = proposal.get("x_key")
    y_keys = proposal.get("y_keys")
    title = proposal.get("title")
    if chart_type not in {"bar", "line", "pie"}:
        raise ValueError("Unsupported chart type.")
    if not rows or x_key not in rows[0] or not isinstance(y_keys, list) or not y_keys:
        raise ValueError("Chart axes are not present in the result.")
    numeric = {
        key for key in rows[0]
        if any(
            isinstance(row.get(key), (int, float))
            and not isinstance(row.get(key), bool)
            for row in rows
        )
    }
    clean_y = [key for key in y_keys if key in numeric][:2]
    if not clean_y:
        raise ValueError("Chart has no real numeric measure.")
    if chart_type == "line" and not DATE_RE.search(str(x_key)):
        raise ValueError("Line charts require a returned date/time dimension.")
    if chart_type == "pie":
        if not PIE_INTENT_RE.search(question) or not 2 <= len(rows) <= 8:
            raise ValueError("Pie chart is not valid for this question/result.")
        values = [row.get(clean_y[0]) for row in rows]
        if not all(isinstance(value, (int, float)) and value >= 0 for value in values):
            raise ValueError("Pie values must be non-negative.")
        clean_y = clean_y[:1]
    return ChartSpec(
        type=chart_type,
        title=str(title).strip()[:100] if title else f"{clean_y[0]} by {x_key}",
        x_key=str(x_key),
        y_keys=clean_y,
    )

from __future__ import annotations

import re
from typing import Any

from app.models.api import ChartSpec


DATE_RE = re.compile(r"date|time|month|year|week|day", re.IGNORECASE)


def build_report(rows: list[dict[str, Any]]) -> tuple[list[str], ChartSpec | None]:
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

    if len(rows) < 2 or not numeric or not dimensions:
        return insights, None
    x_key = next((key for key in dimensions if DATE_RE.search(key)), dimensions[0])
    chart_type = "line" if DATE_RE.search(x_key) else "bar"
    return insights, ChartSpec(
        type=chart_type,
        title=f"{numeric[0].replace('_', ' ').title()} by {x_key.replace('_', ' ').title()}",
        x_key=x_key,
        y_keys=numeric[:2],
    )

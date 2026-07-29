from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


COUNT_RE = re.compile(r"\b(count|how many|number of)\b", re.IGNORECASE)
TOP_RE = re.compile(r"\btop\s+(\d+)\b", re.IGNORECASE)
CHART_RE = re.compile(r"\b(chart|graph|plot|visuali[sz]e)\b", re.IGNORECASE)
ORDER_BY_RE = re.compile(r"\border\s+by\b", re.IGNORECASE)
LIMIT_RE = re.compile(r"\blimit\s+(\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ResultVerification:
    passed: bool
    issues: tuple[str, ...]


def verify_result(
    question: str,
    sql: str,
    rows: list[dict[str, Any]],
) -> ResultVerification:
    """Check deterministic question/result invariants without judging business meaning."""
    issues: list[str] = []
    keys = list(rows[0]) if rows else []
    numeric_keys = [
        key for key in keys
        if any(
            isinstance(row.get(key), (int, float))
            and not isinstance(row.get(key), bool)
            for row in rows
        )
    ]
    dimension_keys = [key for key in keys if key not in numeric_keys]

    if COUNT_RE.search(question) and rows:
        if not any("count" in key.lower() for key in keys) and not (
            len(rows) == 1 and numeric_keys
        ):
            issues.append("The result does not expose the requested count.")

    top_match = TOP_RE.search(question)
    if top_match:
        requested = int(top_match.group(1))
        limit_match = LIMIT_RE.search(sql)
        if not ORDER_BY_RE.search(sql):
            issues.append("A top-N result requires ORDER BY.")
        if not limit_match or int(limit_match.group(1)) > requested:
            issues.append(f"A top-{requested} result requires LIMIT {requested} or less.")
        if len(rows) > requested:
            issues.append(f"The result returned more than the requested top {requested} rows.")

    if CHART_RE.search(question) and len(rows) >= 2:
        if not numeric_keys or not dimension_keys:
            issues.append(
                "The chart request needs a returned dimension and numeric measure."
            )

    return ResultVerification(passed=not issues, issues=tuple(issues))

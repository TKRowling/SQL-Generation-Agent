import pytest

from app.services.cost_guard import validate_explain_plan


def test_accepts_plan_within_cost_limits() -> None:
    result = validate_explain_plan(
        {
            "Plan": {
                "Total Cost": 125.5,
                "Plan Rows": 100,
                "Plans": [{"Total Cost": 20, "Plan Rows": 10}],
            }
        },
        max_cost=1000,
        max_rows=1000,
    )
    assert result.total_cost == 125.5
    assert result.node_count == 2


def test_rejects_expensive_plan() -> None:
    with pytest.raises(ValueError, match="cost"):
        validate_explain_plan(
            {"Plan": {"Total Cost": 5000, "Plan Rows": 100}},
            max_cost=1000,
            max_rows=1000,
        )


def test_rejects_excessive_estimated_rows() -> None:
    with pytest.raises(ValueError, match="Estimated rows"):
        validate_explain_plan(
            {"Plan": {"Total Cost": 50, "Plan Rows": 5000}},
            max_cost=1000,
            max_rows=1000,
        )

from app.services.reporting import build_report, validate_chart_proposal


def test_empty_result_explains_why_no_chart_exists() -> None:
    insights, chart = build_report([], "Show a chart")
    assert chart is None
    assert any("No rows matched" in insight for insight in insights)
    assert any("No chart" in insight for insight in insights)


def test_uses_pie_for_small_part_to_whole_breakdown() -> None:
    rows = [
        {"transaction_type": "TRANSFER", "transaction_count": 60},
        {"transaction_type": "DEPOSIT", "transaction_count": 30},
        {"transaction_type": "WITHDRAWAL", "transaction_count": 10},
    ]
    insights, chart = build_report(
        rows,
        "Show the percentage distribution of transactions by transaction type",
    )
    assert chart is not None
    assert chart.type == "pie"
    assert chart.y_keys == ["transaction_count"]
    assert any("60.0%" in insight for insight in insights)


def test_uses_bar_when_question_is_not_part_to_whole() -> None:
    rows = [
        {"branch": "A", "total_amount": 100},
        {"branch": "B", "total_amount": 80},
    ]
    _, chart = build_report(rows, "Compare total amount by branch")
    assert chart is not None
    assert chart.type == "bar"


def test_uses_line_for_time_series() -> None:
    rows = [
        {"transaction_month": "2026-01", "transaction_count": 10},
        {"transaction_month": "2026-02", "transaction_count": 15},
    ]
    _, chart = build_report(rows, "Show monthly transaction trend")
    assert chart is not None
    assert chart.type == "line"


def test_does_not_use_pie_for_negative_values() -> None:
    rows = [
        {"category": "Profit", "value": 10},
        {"category": "Loss", "value": -2},
    ]
    _, chart = build_report(rows, "Show the percentage breakdown")
    assert chart is not None
    assert chart.type == "bar"


def test_does_not_use_pie_for_too_many_categories() -> None:
    rows = [{"category": f"C{index}", "value": index + 1} for index in range(9)]
    _, chart = build_report(rows, "Show the distribution by category")
    assert chart is not None
    assert chart.type == "bar"


def test_does_not_chart_schema_variable_listing() -> None:
    rows = [
        {"id": 1, "record_uuid": "uuid-1", "amount": 100},
        {"id": 2, "record_uuid": "uuid-2", "amount": 200},
    ]
    _, chart = build_report(rows, "What are the variables in loan applications?")
    assert chart is None


def test_validates_ai_chart_axes_against_exact_result() -> None:
    rows = [
        {"customer_id": "CUS1", "income": 7000},
        {"customer_id": "CUS2", "income": 8000},
    ]
    chart = validate_chart_proposal(
        {
            "type": "bar",
            "title": "Customer income",
            "x_key": "customer_id",
            "y_keys": ["income"],
        },
        rows,
        "Show customer income as a chart",
    )
    assert chart is not None
    assert chart.x_key == "customer_id"
    assert chart.y_keys == ["income"]

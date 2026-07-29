from app.services.result_verifier import verify_result


def test_verifies_top_n_shape() -> None:
    result = verify_result(
        "Show the top 5 accounts by balance",
        "SELECT account_id, balance FROM accounts ORDER BY balance DESC LIMIT 5",
        [{"account_id": str(index), "balance": 100 - index} for index in range(5)],
    )
    assert result.passed


def test_rejects_top_n_without_ordering() -> None:
    result = verify_result(
        "Show the top 5 accounts by balance",
        "SELECT account_id, balance FROM accounts LIMIT 5",
        [{"account_id": "A", "balance": 100}],
    )
    assert not result.passed
    assert "ORDER BY" in result.issues[0]


def test_chart_requires_dimension_and_measure() -> None:
    result = verify_result(
        "Give me a chart",
        "SELECT account_id FROM accounts LIMIT 5",
        [{"account_id": "A"}, {"account_id": "B"}],
    )
    assert not result.passed

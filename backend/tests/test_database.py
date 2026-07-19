import pytest

from app.services.database import normalize_select


def test_adds_limit() -> None:
    assert normalize_select("SELECT id FROM documents", 50).endswith("LIMIT 50")


def test_keeps_existing_limit() -> None:
    assert normalize_select("SELECT id FROM documents LIMIT 5", 50).endswith("LIMIT 5")


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE users SET name='x'",
        "DELETE FROM users",
        "SHOW TABLES",
        "SELECT 1; DROP TABLE users",
        "SELECT * FROM users WHERE id = (INSERT INTO x VALUES (1))",
    ],
)
def test_rejects_unsafe_sql(sql: str) -> None:
    with pytest.raises(ValueError):
        normalize_select(sql, 50)

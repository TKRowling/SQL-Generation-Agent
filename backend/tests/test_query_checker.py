import pytest

from app.services.query_checker import (
    extract_table_references,
    validate_query_against_catalog,
)
from app.services.schema import SchemaCatalog


CATALOG = SchemaCatalog(
    columns={
        "accounts": frozenset({"account_id", "branch_id", "opened_date"}),
        "branches": frozenset({"branch_id", "province"}),
    },
    foreign_keys=(),
)


def test_extracts_tables_and_aliases() -> None:
    references = extract_table_references(
        "SELECT a.account_id FROM accounts a JOIN branches b ON a.branch_id = b.branch_id"
    )
    assert references == (
        (None, "accounts", "a"),
        (None, "branches", "b"),
    )


def test_accepts_approved_tables_and_qualified_columns() -> None:
    result = validate_query_against_catalog(
        "SELECT a.account_id, b.province FROM accounts a "
        "JOIN branches b ON a.branch_id = b.branch_id",
        CATALOG,
        limit=50,
        approved_schema="ai_demo",
    )
    assert result.referenced_tables == ("accounts", "branches")
    assert result.normalized_sql.endswith("LIMIT 50")


def test_rejects_nonexistent_table_before_execution() -> None:
    with pytest.raises(ValueError, match="nonexistent table"):
        validate_query_against_catalog(
            "SELECT account_id FROM accountz",
            CATALOG,
            limit=50,
            approved_schema="ai_demo",
        )


def test_rejects_nonexistent_qualified_column() -> None:
    with pytest.raises(ValueError, match="nonexistent column"):
        validate_query_against_catalog(
            "SELECT a.customer_name FROM accounts a",
            CATALOG,
            limit=50,
            approved_schema="ai_demo",
        )


def test_rejects_select_star_but_allows_count_star() -> None:
    with pytest.raises(ValueError, match=r"SELECT \*"):
        validate_query_against_catalog(
            "SELECT * FROM accounts",
            CATALOG,
            limit=50,
            approved_schema="ai_demo",
        )
    result = validate_query_against_catalog(
        "SELECT COUNT(*) AS account_count FROM accounts",
        CATALOG,
        limit=50,
        approved_schema="ai_demo",
    )
    assert result.referenced_tables == ("accounts",)


def test_ast_allows_read_only_cte_and_tracks_physical_table() -> None:
    result = validate_query_against_catalog(
        "WITH recent AS (SELECT account_id FROM accounts) "
        "SELECT account_id FROM recent",
        CATALOG,
        limit=50,
        approved_schema="ai_demo",
    )
    assert result.referenced_tables == ("accounts",)


def test_ast_rejects_data_modifying_cte() -> None:
    with pytest.raises(ValueError, match="forbidden"):
        validate_query_against_catalog(
            "WITH changed AS (DELETE FROM accounts RETURNING account_id) "
            "SELECT account_id FROM changed",
            CATALOG,
            limit=50,
            approved_schema="ai_demo",
        )


def test_ast_enforces_join_limit() -> None:
    with pytest.raises(ValueError, match="configured maximum"):
        validate_query_against_catalog(
            "SELECT a.account_id FROM accounts a "
            "JOIN branches b ON a.branch_id = b.branch_id",
            CATALOG,
            limit=50,
            approved_schema="ai_demo",
            max_joins=0,
        )

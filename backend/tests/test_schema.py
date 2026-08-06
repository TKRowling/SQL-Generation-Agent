import pytest

from app.core.config import get_settings
from app.services.schema import (
    SchemaCatalog,
    SchemaService,
    build_schema_summary,
    select_relevant_tables,
)


def test_schema_hides_secrets_and_marks_keys() -> None:
    columns = [
        {"table_name": "users", "column_name": "id", "column_type": "bigint", "column_key": "PRI"},
        {"table_name": "users", "column_name": "name", "column_type": "character varying(255)", "column_key": ""},
        {"table_name": "users", "column_name": "password", "column_type": "character varying(255)", "column_key": ""},
        {"table_name": "documents", "column_name": "user_id", "column_type": "bigint", "column_key": ""},
    ]
    fks = [
        {"table_name": "documents", "column_name": "user_id", "ref_table": "users", "ref_column": "id"}
    ]
    result = build_schema_summary(columns, fks)
    assert "id bigint PK" in result
    assert "password" not in result
    assert "user_id bigint ->users.id" in result


def test_selects_relevant_tables_and_fk_neighbours() -> None:
    catalog = SchemaCatalog(
        columns={
            "accounts": frozenset({"account_id", "branch_id"}),
            "branches": frozenset({"branch_id", "province"}),
            "bank_transactions": frozenset({"transaction_id", "account_id", "amount"}),
            "cards": frozenset({"card_id"}),
        },
        foreign_keys=(
            {
                "table_name": "bank_transactions",
                "column_name": "account_id",
                "ref_table": "accounts",
                "ref_column": "account_id",
            },
        ),
    )
    selected = select_relevant_tables(
        "Show transaction amount by account",
        catalog,
        max_tables=3,
    )
    assert "bank_transactions" in selected
    assert "accounts" in selected
    assert "cards" not in selected


def test_semantic_synonyms_retrieve_income_for_salary_question() -> None:
    catalog = SchemaCatalog(
        columns={
            "customer_income": frozenset({"customer_id", "amount"}),
            "customer_contacts": frozenset({"customer_id", "phone"}),
        },
        foreign_keys=(),
    )
    selected = select_relevant_tables(
        "Show the highest customer salary",
        catalog,
        max_tables=1,
    )
    assert selected == ["customer_income"]


@pytest.mark.asyncio
async def test_schema_fingerprint_changes_with_approved_structure(monkeypatch) -> None:
    service = SchemaService()
    schema_name = get_settings().db_schema
    service._cached_columns[schema_name] = [
        {
            "table_name": "customers",
            "column_name": "customer_id",
            "data_type": "bigint",
            "is_nullable": "NO",
            "is_pk": True,
            "is_unique": True,
        }
    ]
    service._cached_foreign_keys[schema_name] = []

    async def keep_seeded_catalog(*_args, **_kwargs):
        return "customers: customer_id bigint PK"

    monkeypatch.setattr(service, "get_summary", keep_seeded_catalog)
    original = await service.get_fingerprint(schema_name)

    service._cached_columns[schema_name].append(
        {
            "table_name": "customers",
            "column_name": "status",
            "data_type": "character varying",
            "is_nullable": "YES",
            "is_pk": False,
            "is_unique": False,
        }
    )
    changed = await service.get_fingerprint(schema_name)

    assert original != changed

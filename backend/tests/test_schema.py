from app.services.schema import SchemaCatalog, build_schema_summary, select_relevant_tables


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

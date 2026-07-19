from app.services.schema import build_schema_summary


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

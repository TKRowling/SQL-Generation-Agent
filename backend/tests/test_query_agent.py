from app.services.query_agent import (
    deterministic_summary,
    extract_sql,
    looks_degenerate,
    looks_like_destructive_request,
    looks_like_database_name_request,
    looks_like_table_list_request,
    looks_like_data_question,
    references_secret_column,
)


def test_extract_sql_from_fence() -> None:
    assert extract_sql("```sql\nSELECT COUNT(*) FROM documents\n```") == "SELECT COUNT(*) FROM documents"


def test_extract_first_statement() -> None:
    assert extract_sql("SELECT 1; DROP TABLE x") == "SELECT 1"


def test_secret_columns() -> None:
    assert references_secret_column("SELECT password FROM users")
    assert references_secret_column("SELECT key_secret FROM keys")
    assert not references_secret_column("SELECT id, name FROM users")


def test_data_question_heuristic() -> None:
    assert looks_like_data_question("How many documents are there?")
    assert looks_like_data_question("List the latest projects")
    assert not looks_like_data_question("Hello, how are you?")


def test_destructive_request_heuristic() -> None:
    assert looks_like_destructive_request("Give me SQL to delete the accounts table")
    assert looks_like_destructive_request("DROP TABLE accounts")
    assert looks_like_destructive_request("Update every account balance")
    assert not looks_like_destructive_request("List deleted accounts")
    assert not looks_like_destructive_request("Show account updates from this week")


def test_metadata_request_heuristics() -> None:
    assert looks_like_table_list_request("List all the tables in the database")
    assert looks_like_table_list_request("What tables are available?")
    assert not looks_like_table_list_request("Show the accounts table")
    assert looks_like_database_name_request("What is the name of the database?")
    assert not looks_like_database_name_request("Show database tables")


def test_degenerate_output() -> None:
    assert looks_degenerate(".Forms.Forms.Forms.Forms.Forms.Forms.Forms")
    assert not looks_degenerate("There are 6 documents.")


def test_deterministic_summary() -> None:
    assert deterministic_summary([], False) == "No matching records were found."
    assert deterministic_summary([{"document_count": 6}], False) == "Document Count: 6"

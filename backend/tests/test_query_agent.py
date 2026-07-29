import pytest

from app.core.errors import UnsupportedDataQuestionError
from app.models.api import ChatMessage
from app.services.query_agent import (
    QueryAgent,
    deterministic_summary,
    extract_sql,
    generation_history,
    looks_degenerate,
    looks_like_destructive_request,
    looks_like_database_name_request,
    looks_like_table_definition_request,
    looks_like_schema_question,
    looks_like_table_list_request,
    looks_like_data_question,
    references_secret_column,
    unsupported_reason,
)


def test_extract_sql_from_fence() -> None:
    assert extract_sql("```sql\nSELECT COUNT(*) FROM documents\n```") == "SELECT COUNT(*) FROM documents"


def test_extract_first_statement() -> None:
    assert extract_sql("SELECT 1; DROP TABLE x") == "SELECT 1"


def test_extracts_unsupported_schema_reason() -> None:
    assert unsupported_reason("UNSUPPORTED: no age or birth-date column exists") == (
        "no age or birth-date column exists"
    )


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
    assert looks_like_table_definition_request(
        "What is the definition of each table name in this schema?"
    )
    assert looks_like_schema_question("What does risk_score mean in loan_applications?")
    assert looks_like_schema_question("Explain the relationship between customers and loans")
    assert not looks_like_schema_question("Show the latest 10 loan applications")
    assert looks_like_table_definition_request(
        "what are they?",
        [
            ChatMessage(
                role="assistant",
                content="Found 15 tables in the customer360 schema.",
            )
        ],
    )


def test_degenerate_output() -> None:
    assert looks_degenerate(".Forms.Forms.Forms.Forms.Forms.Forms.Forms")
    assert not looks_degenerate("There are 6 documents.")


def test_only_clear_followups_inherit_conversation_history() -> None:
    history = [
        ChatMessage(role="user", content="Show customers by salary"),
        ChatMessage(role="assistant", content="That field is unsupported."),
    ]
    assert generation_history(
        "Show the top 10 customers by income amount.", history
    ) == []
    assert generation_history("Only show the top 5.", history) == history


def test_deterministic_summary() -> None:
    assert deterministic_summary([], False) == "No matching records were found."
    assert deterministic_summary([{"document_count": 6}], False) == "Document Count: 6"


@pytest.mark.asyncio
async def test_bounded_recovery_retries_with_new_sql(monkeypatch) -> None:
    agent = QueryAgent()
    attempted: list[str] = []
    generated = iter(["SELECT account_id FROM accounts", "SELECT account_id FROM accounts LIMIT 5"])

    async def run_guarded(sql: str, _schema_name: str):
        attempted.append(sql)
        if len(attempted) < 3:
            raise ValueError("correctable SQL error")
        return [{"account_id": 1}]

    async def generate_sql(*_args, **_kwargs):
        return next(generated)

    async def relevant_summary(*_args, **_kwargs):
        return "accounts: account_id bigint PK"

    monkeypatch.setattr(agent, "_run_guarded", run_guarded)
    monkeypatch.setattr(agent, "_generate_sql", generate_sql)
    monkeypatch.setattr(
        "app.services.query_agent.schema_service.get_relevant_summary",
        relevant_summary,
    )

    sql, rows = await agent._run_with_retry(
        "List accounts",
        "accounts: account_id bigint PK",
        "SELECT id FROM accounts",
        [],
        "public",
    )
    assert len(attempted) == 3
    assert sql == "SELECT account_id FROM accounts LIMIT 5"
    assert rows == [{"account_id": 1}]


@pytest.mark.asyncio
async def test_unsupported_result_stops_after_catalog_recheck(monkeypatch) -> None:
    agent = QueryAgent()

    async def relevant_summary(*_args, **_kwargs):
        return "customers: customer_id varchar"

    async def generate_sql(*_args, **_kwargs):
        return "UNSUPPORTED: no age column exists"

    monkeypatch.setattr(
        "app.services.query_agent.schema_service.get_relevant_summary",
        relevant_summary,
    )
    monkeypatch.setattr(agent, "_generate_sql", generate_sql)

    with pytest.raises(UnsupportedDataQuestionError, match="no age column"):
        await agent._run_with_retry(
            "List customers aged 19 to 21",
            "customers: customer_id varchar",
            "UNSUPPORTED: no age column exists",
            [],
            "customer360",
        )


@pytest.mark.asyncio
async def test_unsupported_claim_can_recover_using_complete_catalog(monkeypatch) -> None:
    agent = QueryAgent()
    histories: list[list[ChatMessage]] = []

    async def relevant_summary(*_args, **kwargs):
        assert kwargs["max_tables"] == 50
        assert kwargs["force"] is True
        return "customer_income: customer_id varchar, amount numeric"

    async def generate_sql(_question, _schema, history, _prior_error):
        histories.append(history)
        return (
            "SELECT customer_id, SUM(amount) AS total_income "
            "FROM customer_income GROUP BY customer_id "
            "ORDER BY total_income DESC LIMIT 10"
        )

    async def run_guarded(_sql, _schema):
        return [{"customer_id": "CUS1", "total_income": 100}]

    monkeypatch.setattr(
        "app.services.query_agent.schema_service.get_relevant_summary",
        relevant_summary,
    )
    monkeypatch.setattr(agent, "_generate_sql", generate_sql)
    monkeypatch.setattr(agent, "_run_guarded", run_guarded)

    sql, rows = await agent._run_with_retry(
        "Show the top 10 customers by income amount",
        "customer_income: customer_id varchar, amount numeric",
        "UNSUPPORTED: income relationship not found",
        [ChatMessage(role="user", content="salary")],
        "customer360",
    )

    assert histories == [[]]
    assert "customer_income" in sql
    assert rows == [{"customer_id": "CUS1", "total_income": 100}]

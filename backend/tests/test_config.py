import pytest

from app.core.config import Settings, parse_db_url


def test_parse_jdbc_url() -> None:
    db = parse_db_url(
        "jdbc:postgresql://db.example.com:6543/askme",
        "reader",
        "secret",
    )
    assert db.host == "db.example.com"
    assert db.port == 6543
    assert db.database == "askme"
    assert db.user == "reader"


def test_url_credentials_take_priority() -> None:
    db = parse_db_url(
        "postgresql://url-user:url%40pass@db.example.com/mydb",
        "env",
        "env-pass",
    )
    assert db.user == "url-user"
    assert db.password == "url@pass"


def test_default_port_and_postgres_alias() -> None:
    db = parse_db_url("postgres://reader:secret@db.example.com/mydb")
    assert db.port == 5432


def test_reads_sslmode() -> None:
    db = parse_db_url("postgresql://reader:secret@localhost/mydb?sslmode=disable")
    assert db.sslmode == "disable"


def test_rejects_mysql_url() -> None:
    with pytest.raises(ValueError):
        parse_db_url("mysql://reader:secret@localhost/mydb")


def test_resolves_only_approved_schemas() -> None:
    settings = Settings(
        db_schema="finance",
        db_schemas="finance,loans,cards",
        _env_file=None,
    )
    assert settings.allowed_schemas == ("finance", "loans", "cards")
    assert settings.resolve_schema("LOANS") == "loans"
    with pytest.raises(ValueError, match="not approved"):
        settings.resolve_schema("payroll")


def test_ollama_is_configured_without_api_key() -> None:
    settings = Settings(
        ollama_base_url="http://127.0.0.1:11434/",
        ollama_model="llama3.1:8b",
        _env_file=None,
    )
    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    assert settings.ollama_chat_path == "/api/chat"
    assert settings.ollama_trust_env is False
    assert settings.ai_configured

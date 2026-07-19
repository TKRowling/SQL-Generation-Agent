from app.services.prompt_loader import load_skill_prompts


def test_loads_runtime_skill_sections() -> None:
    prompts = load_skill_prompts(50)
    assert "exactly one executable PostgreSQL SELECT" in prompts.sql_rules
    assert "at most 50 rows" in prompts.sql_rules
    assert "authoritative database results" in prompts.summary_rules
    assert "Never substitute a familiar or similar table name" in prompts.sql_rules
    assert "Never propose, quote, or explain INSERT" in prompts.summary_rules

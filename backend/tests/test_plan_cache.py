import sqlite3

import pytest

from app.services.plan_cache import PlanCache, normalize_question, question_hash


def test_question_normalization_is_stable() -> None:
    first = "  Show   the top 10 customers? "
    second = "show the top 10 customers."
    assert normalize_question(first) == normalize_question(second)
    assert question_hash(first) == question_hash(second)


@pytest.mark.asyncio
async def test_plan_cache_persists_by_schema_fingerprint(tmp_path) -> None:
    path = tmp_path / "plans.sqlite3"
    cache = PlanCache(path)
    question = "Show the top 10 customers by income"
    sql = "SELECT customer_id, amount FROM customer_income ORDER BY amount DESC LIMIT 10"

    await cache.put(question, "customer360", "schema-v1", sql)

    restarted_cache = PlanCache(path)
    assert await restarted_cache.get(question, "customer360", "schema-v1") == sql
    assert await restarted_cache.get(question, "customer360", "schema-v2") is None
    assert await restarted_cache.get(question, "loans", "schema-v1") is None

    with sqlite3.connect(path) as connection:
        stored = connection.execute(
            "SELECT question_hash, sql FROM validated_plans"
        ).fetchone()
    assert stored is not None
    assert stored[0] == question_hash(question)
    assert stored[1] == sql


@pytest.mark.asyncio
async def test_plan_cache_delete_removes_rejected_plan(tmp_path) -> None:
    cache = PlanCache(tmp_path / "plans.sqlite3")
    await cache.put("List accounts", "accounts", "v1", "SELECT id FROM accounts")
    await cache.delete("List accounts", "accounts", "v1")
    assert await cache.get("List accounts", "accounts", "v1") is None

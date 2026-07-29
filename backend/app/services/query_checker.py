from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from app.core.config import get_settings
from app.services.database import enforce_access_policy
from app.services.schema import SchemaCatalog, schema_service


FORBIDDEN_AST_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Command,
    exp.Transaction,
)


@dataclass(frozen=True)
class QueryCheckResult:
    normalized_sql: str
    referenced_tables: tuple[str, ...]
    projected_columns: tuple[str, ...]
    join_count: int


def _parse_one_select(sql: str) -> exp.Select:
    try:
        statements = parse(sql.strip(), read="postgres")
    except ParseError as exc:
        raise ValueError(f"Invalid PostgreSQL SQL: {exc}") from exc
    if len(statements) != 1:
        raise ValueError("Exactly one SQL statement is allowed.")
    statement = statements[0]
    if not isinstance(statement, exp.Select):
        raise ValueError("Only SELECT queries are allowed.")
    if any(statement.find(node_type) for node_type in FORBIDDEN_AST_TYPES):
        raise ValueError("The SELECT contains a forbidden database-changing operation.")
    return statement


def _is_count_star(star: exp.Star) -> bool:
    return isinstance(star.parent, exp.Count)


def extract_table_references(sql: str) -> tuple[tuple[str | None, str, str], ...]:
    """Expose AST-derived table references for diagnostics and compatibility."""
    statement = _parse_one_select(sql)
    cte_names = {
        cte.alias_or_name.lower()
        for cte in statement.find_all(exp.CTE)
        if cte.alias_or_name
    }
    return tuple(
        (
            table.db or None,
            table.name,
            table.alias_or_name or table.name,
        )
        for table in statement.find_all(exp.Table)
        if table.name.lower() not in cte_names
    )


def validate_query_against_catalog(
    sql: str,
    catalog: SchemaCatalog,
    *,
    limit: int,
    approved_schema: str,
    max_joins: int = 8,
) -> QueryCheckResult:
    """Parse PostgreSQL SQL and authorize its AST against approved metadata."""
    enforce_access_policy(sql)
    statement = _parse_one_select(sql)

    stars = list(statement.find_all(exp.Star))
    if any(not _is_count_star(star) for star in stars):
        raise ValueError("SELECT * is not allowed; choose explicit approved columns.")

    cte_names = {
        cte.alias_or_name.lower()
        for cte in statement.find_all(exp.CTE)
        if cte.alias_or_name
    }
    approved = {table.lower(): table for table in catalog.columns}
    aliases: dict[str, str] = {}
    referenced: list[str] = []

    for table_expression in statement.find_all(exp.Table):
        raw_table = table_expression.name
        if raw_table.lower() in cte_names:
            continue
        schema = table_expression.db
        table = approved.get(raw_table.lower())
        if table is None:
            raise ValueError(
                f"Query references unapproved or nonexistent table: {raw_table}"
            )
        if schema and schema.lower() != approved_schema.lower():
            raise ValueError(f"Query references unapproved schema: {schema}")
        alias = table_expression.alias_or_name or table
        aliases[alias.lower()] = table
        aliases[table.lower()] = table
        if table not in referenced:
            referenced.append(table)

    if not referenced:
        raise ValueError("A data query must reference at least one approved table.")

    for column in statement.find_all(exp.Column):
        if isinstance(column.this, exp.Star):
            continue
        owner = column.table
        if not owner:
            if len(referenced) == 1:
                allowed = {item.lower() for item in catalog.columns[referenced[0]]}
                if column.name.lower() not in allowed:
                    # ORDER BY and GROUP BY may reference a SELECT alias.
                    aliases_in_select = {
                        expression.alias.lower()
                        for expression in statement.expressions
                        if expression.alias
                    }
                    if column.name.lower() not in aliases_in_select:
                        raise ValueError(
                            f"Query references nonexistent column: {column.name}"
                        )
            continue
        table = aliases.get(owner.lower())
        if table is None:
            if owner.lower() == approved_schema.lower():
                continue
            raise ValueError(f"Query references unknown table alias: {owner}")
        allowed = {item.lower() for item in catalog.columns[table]}
        if column.name.lower() not in allowed:
            raise ValueError(
                f"Query references nonexistent column: {owner}.{column.name}"
            )

    join_count = sum(1 for _ in statement.find_all(exp.Join))
    if join_count > max_joins:
        raise ValueError(
            f"Query has {join_count} joins; the configured maximum is {max_joins}."
        )

    if statement.args.get("limit") is None:
        statement = statement.limit(limit)
    normalized = statement.sql(dialect="postgres")
    projected = tuple(
        expression.alias_or_name
        for expression in statement.expressions
        if expression.alias_or_name
    )
    return QueryCheckResult(
        normalized_sql=normalized,
        referenced_tables=tuple(referenced),
        projected_columns=projected,
        join_count=join_count,
    )


class QueryChecker:
    async def check(self, sql: str, schema: str | None = None) -> QueryCheckResult:
        settings = get_settings()
        selected_schema = settings.resolve_schema(schema)
        catalog = await schema_service.get_catalog(selected_schema)
        return validate_query_against_catalog(
            sql,
            catalog,
            limit=settings.max_rows,
            approved_schema=selected_schema,
            max_joins=settings.db_explain_max_joins,
        )


query_checker = QueryChecker()

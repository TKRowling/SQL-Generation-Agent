from __future__ import annotations

import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.core.config import get_settings
from app.core.errors import (
    DatabaseUnavailableError,
    ForbiddenQueryError,
    UnsupportedDataQuestionError,
)
from app.agents.debug import traced_node
from app.agents.state import AgentState, MultiAgentAnswer
from app.agents.tools import (
    execute_readonly_sql,
    explain_query_cost,
    get_schema_fingerprint,
    search_approved_schema,
    validate_select_sql,
    verify_query_result,
)
from app.services.plan_cache import plan_cache
from app.services.query_agent import (
    RouteAnswer,
    generation_history,
    looks_like_data_question,
    looks_like_database_name_request,
    looks_like_schema_question,
    looks_like_table_definition_request,
    looks_like_table_list_request,
    query_agent,
    unsupported_reason,
)
from app.models.api import ChatMessage
from app.services.reporting import build_report_with_ai


def _normalized_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().casefold()


class AskMeMultiAgentSystem:
    """Build and run the bounded LangGraph multi-agent workflow."""

    def __init__(self) -> None:
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("supervisor", traced_node("supervisor", self._supervisor))
        graph.add_node("metadata_agent", traced_node("metadata_agent", self._metadata_agent))
        graph.add_node("schema_agent", traced_node("schema_agent", self._schema_agent))
        graph.add_node("sql_agent", traced_node("sql_agent", self._sql_agent))
        graph.add_node("validate_tool", traced_node("validate_tool", self._validate_tool))
        graph.add_node("explain_tool", traced_node("explain_tool", self._explain_tool))
        graph.add_node("execute_tool", traced_node("execute_tool", self._execute_tool))
        graph.add_node("verify_tool", traced_node("verify_tool", self._verify_tool))
        graph.add_node("correction_agent", traced_node("correction_agent", self._correction_agent))
        graph.add_node("reporting_agent", traced_node("reporting_agent", self._reporting_agent))
        graph.add_node("chat_agent", traced_node("chat_agent", self._chat_agent))
        graph.add_node("failed", traced_node("failed", self._failed))

        graph.add_edge(START, "supervisor")
        graph.add_conditional_edges(
            "supervisor",
            lambda state: state["route"],
            {
                "metadata": "metadata_agent",
                "sql": "schema_agent",
                "chat": "chat_agent",
            },
        )
        graph.add_edge("metadata_agent", "reporting_agent")
        graph.add_edge("schema_agent", "sql_agent")
        graph.add_conditional_edges(
            "sql_agent",
            lambda state: state.get("route", "sql"),
            {"sql": "validate_tool", "chat": "chat_agent"},
        )
        graph.add_conditional_edges(
            "validate_tool", self._after_guard, {"continue": "explain_tool", "retry": "correction_agent", "fail": "failed"}
        )
        graph.add_conditional_edges(
            "explain_tool", self._after_guard, {"continue": "execute_tool", "retry": "correction_agent", "fail": "failed"}
        )
        graph.add_conditional_edges(
            "execute_tool", self._after_guard, {"continue": "verify_tool", "retry": "correction_agent", "fail": "failed"}
        )
        graph.add_conditional_edges(
            "verify_tool", self._after_verify, {"success": "reporting_agent", "retry": "correction_agent", "fail": "failed"}
        )
        graph.add_edge("correction_agent", "validate_tool")
        graph.add_edge("reporting_agent", END)
        graph.add_edge("chat_agent", END)
        return graph.compile()

    async def _supervisor(self, state: AgentState) -> dict[str, Any]:
        question = state["question"]
        history = state.get("history", [])
        metadata = (
            looks_like_database_name_request(question)
            or looks_like_table_list_request(question)
            or looks_like_table_definition_request(question, history)
            or looks_like_schema_question(question)
        )
        if metadata and not state.get("force_data"):
            route = "metadata"
        elif state.get("force_data") or looks_like_data_question(question):
            route = "sql"
        else:
            # The SQL agent performs a schema-grounded probe and may hand off to chat.
            route = "sql"
        return {"route": route, "attempt": 1, "attempted_sql": []}

    async def _metadata_agent(self, state: AgentState) -> dict[str, Any]:
        result = await query_agent.answer_metadata(
            state["question"], state["schema_name"], state.get("history", [])
        )
        if result is None:
            return {"route": "chat"}
        return {
            "kind": "data",
            "answer": result.answer,
            "rows": result.rows,
            "sql": result.sql,
        }

    async def _schema_agent(self, state: AgentState) -> dict[str, Any]:
        relevant_history = generation_history(
            state["question"], state.get("history", [])
        )
        history_terms = " ".join(
            message.content for message in relevant_history if message.role == "user"
        )
        schema_context = await search_approved_schema.ainvoke(
            {
                "question": state["question"],
                "schema_name": state["schema_name"],
                "additional_terms": history_terms,
            }
        )
        fingerprint = await get_schema_fingerprint.ainvoke(
            {"schema_name": state["schema_name"]}
        )
        return {
            "schema_context": schema_context,
            "schema_fingerprint": fingerprint,
        }

    async def _sql_agent(self, state: AgentState) -> dict[str, Any]:
        question = state["question"]
        history = generation_history(question, state.get("history", []))
        fingerprint = state["schema_fingerprint"]
        cached = await plan_cache.get(question, state["schema_name"], fingerprint)
        if cached:
            return {"sql": cached, "cached_plan": True, "route": "sql"}

        if state.get("force_data") or looks_like_data_question(question):
            sql = await query_agent._generate_sql(
                question, state["schema_context"], history
            )
        else:
            sql = await query_agent._generate_sql_or_chat(
                question, state["schema_context"], history
            )
            if sql is None:
                return {"route": "chat"}
        return {"sql": sql, "cached_plan": False, "route": "sql"}

    async def _validate_tool(self, state: AgentState) -> dict[str, Any]:
        sql = state["sql"]
        reason = unsupported_reason(sql)
        if reason:
            return {"error": f"UNSUPPORTED: {reason}"}
        attempted = [*state.get("attempted_sql", []), _normalized_sql(sql)]
        try:
            checked = await validate_select_sql.ainvoke(
                {"sql": sql, "schema_name": state["schema_name"]}
            )
            return {
                "normalized_sql": checked["normalized_sql"],
                "sql": checked["normalized_sql"],
                "attempted_sql": attempted,
                "error": "",
            }
        except Exception as exc:
            if isinstance(exc, ForbiddenQueryError):
                return {"error": str(exc), "fatal_error": True, "exception": exc}
            return {"error": f"SQL validation failed: {exc}", "attempted_sql": attempted}

    async def _explain_tool(self, state: AgentState) -> dict[str, Any]:
        try:
            await explain_query_cost.ainvoke(
                {"sql": state["sql"], "schema_name": state["schema_name"]}
            )
            return {"error": ""}
        except Exception as exc:
            if isinstance(exc, DatabaseUnavailableError):
                return {"error": str(exc), "fatal_error": True, "exception": exc}
            return {"error": f"EXPLAIN cost guard failed: {exc}"}

    async def _execute_tool(self, state: AgentState) -> dict[str, Any]:
        try:
            rows = await execute_readonly_sql.ainvoke(
                {"sql": state["sql"], "schema_name": state["schema_name"]}
            )
            return {"rows": rows, "error": ""}
        except Exception as exc:
            if isinstance(exc, DatabaseUnavailableError):
                return {"error": str(exc), "fatal_error": True, "exception": exc}
            return {"error": f"Read-only execution failed: {exc}"}

    async def _verify_tool(self, state: AgentState) -> dict[str, Any]:
        rows = state.get("rows", [])
        if not rows and state.get("attempt", 1) < get_settings().sql_max_attempts:
            return {
                "error": (
                    "The valid query returned zero rows. Re-check table selection, joins, "
                    "types, and implicit date assumptions without removing explicit filters."
                )
            }
        checked = await verify_query_result.ainvoke(
            {"question": state["question"], "sql": state["sql"], "rows": rows}
        )
        if not checked["passed"]:
            return {"error": "Result verification failed: " + "; ".join(checked["issues"])}
        await plan_cache.put(
            state["question"],
            state["schema_name"],
            state["schema_fingerprint"],
            state["sql"],
        )
        return {"error": ""}

    def _after_guard(self, state: AgentState) -> str:
        if not state.get("error"):
            return "continue"
        if state.get("fatal_error"):
            return "fail"
        return "retry" if state.get("attempt", 1) < get_settings().sql_max_attempts else "fail"

    def _after_verify(self, state: AgentState) -> str:
        if not state.get("error"):
            return "success"
        return "retry" if state.get("attempt", 1) < get_settings().sql_max_attempts else "fail"

    async def _correction_agent(self, state: AgentState) -> dict[str, Any]:
        attempt = state.get("attempt", 1) + 1
        if state.get("cached_plan"):
            await plan_cache.delete(
                state["question"], state["schema_name"], state["schema_fingerprint"]
            )
        settings = get_settings()
        schema_context = await search_approved_schema.ainvoke(
            {
                "question": state["question"],
                "schema_name": state["schema_name"],
                "additional_terms": f"{state.get('sql', '')}\n{state.get('error', '')}",
                "max_tables": min(50, settings.schema_max_tables * attempt),
                "force_refresh": state.get("error", "").startswith("UNSUPPORTED:"),
            }
        )
        sql = await query_agent._generate_sql(
            state["question"],
            schema_context,
            generation_history(state["question"], state.get("history", [])),
            (
                f"Attempt {attempt - 1} failed: {state.get('error', '')}. "
                "Return a different corrected SELECT using only approved metadata."
            ),
        )
        if _normalized_sql(sql) in state.get("attempted_sql", []):
            if not state.get("rows"):
                # Repeating a valid empty query confirms the authoritative empty result.
                return {"sql": sql, "attempt": settings.sql_max_attempts, "error": ""}
            return {
                "sql": sql,
                "attempt": settings.sql_max_attempts,
                "error": "The SQL agent repeated a previously rejected query.",
            }
        return {
            "sql": sql,
            "schema_context": schema_context,
            "attempt": attempt,
            "cached_plan": False,
            "error": "",
            "rows": [],
        }

    async def _reporting_agent(self, state: AgentState) -> dict[str, Any]:
        rows = state.get("rows", [])
        answer = state.get("answer")
        if answer is None:
            answer = await query_agent._summarize(
                state["question"], state.get("sql", ""), rows
            )
        insights, chart = await build_report_with_ai(rows, state["question"])
        return {
            "kind": "data",
            "answer": answer,
            "insights": insights,
            "chart": chart,
        }

    async def _chat_agent(self, state: AgentState) -> dict[str, Any]:
        result: RouteAnswer = await query_agent._chat(
            state["question"],
            state.get("history", []),
            state["system_prompt"],
        )
        return {
            "kind": "chat",
            "answer": result.answer,
            "rows": [],
            "insights": [],
            "chart": None,
        }

    async def _failed(self, state: AgentState) -> dict[str, Any]:
        if state.get("exception") is not None:
            raise state["exception"]
        reason = state.get("error", "The bounded agent loop was exhausted.")
        unsupported = unsupported_reason(reason)
        if unsupported:
            raise UnsupportedDataQuestionError(
                f"I cannot answer this from the {state['schema_name']} schema because {unsupported}"
            )
        raise UnsupportedDataQuestionError(
            f"The SQL agent could not produce a verified SELECT after "
            f"{state.get('attempt', 1)} bounded attempts: {reason}"
        )

    async def run(
        self,
        question: str,
        schema_name: str,
        history: list[ChatMessage],
        system_prompt: str,
        force_data: bool = False,
    ) -> MultiAgentAnswer:
        final = await self.graph.ainvoke(
            {
                "question": question,
                "schema_name": schema_name,
                "history": history,
                "system_prompt": system_prompt,
                "force_data": force_data,
            },
            config={"recursion_limit": 30},
        )
        return MultiAgentAnswer(
            kind=final.get("kind", "chat"),
            answer=final.get("answer", ""),
            rows=final.get("rows", []),
            sql=final.get("sql"),
            insights=final.get("insights", []),
            chart=final.get("chart"),
        )


multi_agent_system = AskMeMultiAgentSystem()

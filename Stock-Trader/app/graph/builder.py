"""Graph builder for the stock trading agent."""

from __future__ import annotations

from contextlib import ExitStack

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.graph.routes import (
    route_after_buy_preparation,
    route_after_llm,
    route_after_portfolio,
)
from app.graph.state import AgentState
from app.graph.nodes.buy_stock_node import buy_stock_node
from app.graph.nodes.cancel_node import cancel_node
from app.graph.nodes.currency_node import currency_node
from app.graph.nodes.execute_buy_node import execute_buy_node
from app.graph.nodes.llm_node import llm_node
from app.graph.nodes.portfolio_node import portfolio_node
from app.graph.nodes.reply_node import reply_node
from app.graph.nodes.tool_executor_node import tool_executor_node
from app.utils.logging import log_event

try:
    from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore
except ImportError:  # pragma: no cover - depends on optional package availability
    SqliteSaver = None

_CHECKPOINTER_STACK = ExitStack()


def _create_checkpointer(checkpoint_path: str):
    """Create a valid checkpointer instance for the installed LangGraph version."""

    if SqliteSaver is None:
        log_event("graph_compiled", checkpointer="memory", checkpoint_path=checkpoint_path)
        return MemorySaver()

    try:
        sqlite_candidate = SqliteSaver.from_conn_string(checkpoint_path)
        if hasattr(sqlite_candidate, "__enter__") and hasattr(sqlite_candidate, "__exit__"):
            sqlite_saver = _CHECKPOINTER_STACK.enter_context(sqlite_candidate)
        else:
            sqlite_saver = sqlite_candidate

        log_event("graph_compiled", checkpointer="sqlite", checkpoint_path=checkpoint_path)
        return sqlite_saver
    except Exception as exc:  # pragma: no cover - depends on local sqlite package/version behavior
        log_event(
            "graph_compiled",
            checkpointer="memory",
            checkpoint_path=checkpoint_path,
            fallback_reason=str(exc),
        )
        return MemorySaver()


def build_graph(*, checkpoint_path: str = "data/checkpoints.sqlite"):
    """Construct and compile the LangGraph workflow."""

    graph_builder = StateGraph(AgentState)

    graph_builder.add_node("llm_node", llm_node)
    graph_builder.add_node("portfolio_node", portfolio_node)
    graph_builder.add_node("tool_executor_node", tool_executor_node)
    graph_builder.add_node("currency_node", currency_node)
    graph_builder.add_node("buy_stock_node", buy_stock_node)
    graph_builder.add_node("execute_buy_node", execute_buy_node)
    graph_builder.add_node("cancel_node", cancel_node)
    graph_builder.add_node("reply_node", reply_node)

    graph_builder.add_edge(START, "llm_node")
    graph_builder.add_conditional_edges(
        "llm_node",
        route_after_llm,
        {
            "portfolio_node": "portfolio_node",
            "tool_executor_node": "tool_executor_node",
            "buy_stock_node": "buy_stock_node",
            "reply_node": "reply_node",
        },
    )
    graph_builder.add_conditional_edges(
        "portfolio_node",
        route_after_portfolio,
        {
            "currency_node": "currency_node",
            "reply_node": "reply_node",
        },
    )
    graph_builder.add_edge("tool_executor_node", "reply_node")
    graph_builder.add_conditional_edges(
        "buy_stock_node",
        route_after_buy_preparation,
        {
            "execute_buy_node": "execute_buy_node",
            "cancel_node": "cancel_node",
            "reply_node": "reply_node",
        },
    )
    graph_builder.add_edge("currency_node", "reply_node")
    graph_builder.add_edge("execute_buy_node", "reply_node")
    graph_builder.add_edge("cancel_node", "reply_node")
    graph_builder.add_edge("reply_node", END)

    checkpointer = _create_checkpointer(checkpoint_path)
    return graph_builder.compile(checkpointer=checkpointer)

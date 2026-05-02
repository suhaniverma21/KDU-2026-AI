from __future__ import annotations

import logging
import random

from pydantic import BaseModel, Field

from crewai.tools import BaseTool


LOGGER = logging.getLogger(__name__)


class FlakyResearchInput(BaseModel):
    """Input schema for the flaky research tool."""

    query: str = Field(..., description="The research query to investigate.")


class FlakyResearchTool(BaseTool):
    """A synthetic research tool that times out intermittently."""

    name: str = "flaky_research_tool"
    description: str = (
        "Returns a synthetic research note for a query, but intermittently raises "
        "TimeoutError to simulate an unreliable upstream dependency."
    )
    args_schema: type[BaseModel] = FlakyResearchInput
    failure_rate: float = 0.5

    def _run(self, query: str) -> str:
        if random.random() < self.failure_rate:
            LOGGER.warning("FlakyResearchTool timed out for query: %s", query)
            raise TimeoutError("Simulated intermittent timeout in FlakyResearchTool")

        LOGGER.info("FlakyResearchTool succeeded for query: %s", query)
        return (
            f"Synthetic research note for '{query}': "
            "enterprise teams prefer smaller, cheaper models for iterative workflows when "
            "latency and operating cost matter more than peak generation quality."
        )

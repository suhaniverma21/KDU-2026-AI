"""Defines lightweight agent interfaces for coordinator and worker roles."""

from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """Provides the shared execution interface for Phase 2 agents."""

    @abstractmethod
    def run(self, *args, **kwargs):
        """Execute the agent and return its result payload."""

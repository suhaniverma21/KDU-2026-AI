"""Provides shared agent interfaces and abstract execution contracts."""

from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """Defines the minimal interface shared by orchestration-managed agents."""

    @abstractmethod
    def run(self, *args, **kwargs):
        """Execute the agent and return its result."""

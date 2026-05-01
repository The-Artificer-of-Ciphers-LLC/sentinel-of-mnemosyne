"""Context budget policy for message processing."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextBudget:
    sessions_budget: int
    search_budget: int


class ContextBudgetPolicy:
    """Allocate token budgets for hot/warm context tiers."""

    def __init__(self, sessions_ratio: float = 0.15, search_ratio: float = 0.10) -> None:
        self._sessions_ratio = sessions_ratio
        self._search_ratio = search_ratio

    def allocate(self, context_window: int) -> ContextBudget:
        return ContextBudget(
            sessions_budget=int(context_window * self._sessions_ratio),
            search_budget=int(context_window * self._search_ratio),
        )

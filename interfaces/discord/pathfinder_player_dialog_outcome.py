"""Outcome vocabulary for Pathfinder player onboarding dialog actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DialogOutcome:
    """Rendered dialog outcome after lifecycle side effects are complete.

    ``message`` means the caller should render ``content``. ``suppressed`` means
    the dialog already posted directly, usually to preserve send-before-archive
    ordering for terminal lifecycle actions.
    """

    kind: Literal["message", "suppressed"]
    content: str = ""

    @classmethod
    def message(cls, content: str) -> "DialogOutcome":
        return cls(kind="message", content=content)

    @classmethod
    def suppressed(cls) -> "DialogOutcome":
        return cls(kind="suppressed")

    def to_router_response(self) -> str | dict:
        if self.kind == "suppressed":
            return {"type": "suppressed"}
        return self.content

    def to_pathfinder_response(self):
        from pathfinder_types import PathfinderResponse

        if self.kind == "suppressed":
            return PathfinderResponse(kind="suppressed")
        return PathfinderResponse(kind="text", content=self.content)

    def to_legacy_text(self) -> str:
        if self.kind == "suppressed":
            return ""
        return self.content

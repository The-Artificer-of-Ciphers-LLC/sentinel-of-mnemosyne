"""Background task scheduling seam."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Protocol


class TaskRunner(Protocol):
    def schedule(self, coro: Awaitable[object]) -> object:
        ...


class AsyncioTaskRunner:
    def schedule(self, coro: Awaitable[object]) -> object:
        return asyncio.create_task(coro)

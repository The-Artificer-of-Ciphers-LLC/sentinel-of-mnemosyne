import asyncio

from app.services.task_runner import AsyncioTaskRunner


def test_asyncio_task_runner_uses_create_task(monkeypatch):
    called = {"count": 0}

    def _fake_create_task(coro):
        called["count"] += 1
        # close coroutine to avoid warnings in test
        coro.close()
        return object()

    monkeypatch.setattr(asyncio, "create_task", _fake_create_task)

    async def _work():
        return None

    runner = AsyncioTaskRunner()
    runner.schedule(_work())

    assert called["count"] == 1

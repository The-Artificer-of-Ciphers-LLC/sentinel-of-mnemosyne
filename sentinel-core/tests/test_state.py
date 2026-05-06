from types import SimpleNamespace

import pytest

from app.state import RouteContext, get_route_context


class _FakeVault:
    pass


def _make_request_with_state(state: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_get_route_context_returns_pinned_context():
    ctx = RouteContext(vault=_FakeVault())
    request = _make_request_with_state(SimpleNamespace(route_ctx=ctx))

    result = get_route_context(request)

    assert result is ctx


def test_get_route_context_raises_when_missing():
    request = _make_request_with_state(SimpleNamespace())

    with pytest.raises(RuntimeError, match="route_ctx not configured"):
        get_route_context(request)

"""Direct tests for core_gateway seam."""

from unittest.mock import AsyncMock, patch

import httpx

import core_gateway


def test_format_classify_response_filed_with_confidence():
    out = core_gateway.format_classify_response({"action": "filed", "path": "x.md", "confidence": 0.9})
    assert "x.md" in out
    assert "0.9" in out


def test_format_classify_response_inboxed():
    out = core_gateway.format_classify_response({"action": "inboxed"})
    assert "Inboxed" in out


def _mock_get_client(response=None, exc=None):
    """Build a patched httpx.AsyncClient whose .get() returns response or raises exc."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    if exc is not None:
        mock_client.get = AsyncMock(side_effect=exc)
    else:
        mock_client.get = AsyncMock(return_value=response)
    return mock_client


async def test_call_core_graph_formats_response():
    body = {
        "note_count": 42,
        "orphans": ["a.md", "b.md"],
        "backlinks": {},
        "hub_count": 3,
        "link_density": 0.512,
        "caveat": None,
    }
    with patch("core_gateway.httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = _mock_get_client(
            response=httpx.Response(200, json=body, request=httpx.Request("GET", "http://core/vault/graph"))
        )
        out = await core_gateway.call_core_graph(user_id="u1", core_url="http://core", api_key="k")

    assert "42" in out
    assert "2 orphans" in out
    assert "3 hubs" in out
    assert "0.51" in out


async def test_call_core_graph_transport_error_returns_friendly_string():
    with patch("core_gateway.httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = _mock_get_client(exc=httpx.ConnectError("boom"))
        out = await core_gateway.call_core_graph(user_id="u1", core_url="http://core", api_key="k")

    assert "failed" in out.lower()
    assert "boom" in out


async def test_call_core_stats_formats_response():
    body = {
        "note_count": 10,
        "hub_count": 2,
        "orphan_count": 1,
        "avg_notes_per_hub": 5.0,
        "link_density": 0.25,
        "caveat": None,
    }
    with patch("core_gateway.httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = _mock_get_client(
            response=httpx.Response(200, json=body, request=httpx.Request("GET", "http://core/vault/stats"))
        )
        out = await core_gateway.call_core_stats(user_id="u1", core_url="http://core", api_key="k")

    assert "10" in out
    assert "2 hubs" in out
    assert "1 orphans" in out
    assert "5.0" in out
    assert "0.25" in out


async def test_call_core_stats_transport_error_returns_friendly_string():
    with patch("core_gateway.httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = _mock_get_client(exc=httpx.ConnectError("boom"))
        out = await core_gateway.call_core_stats(user_id="u1", core_url="http://core", api_key="k")

    assert "failed" in out.lower()
    assert "boom" in out


async def test_call_core_check_formats_response_with_failures():
    body = {
        "note_count": 3,
        "compliant_count": 2,
        "results": [
            {
                "path": "notes/a.md",
                "has_schema": True,
                "has_type": True,
                "has_claim_title": True,
                "has_wikilink": True,
                "failures": [],
            },
            {
                "path": "notes/b.md",
                "has_schema": False,
                "has_type": False,
                "has_claim_title": True,
                "has_wikilink": True,
                "failures": ["missing _schema"],
            },
        ],
        "caveat": None,
    }
    with patch("core_gateway.httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = _mock_get_client(
            response=httpx.Response(200, json=body, request=httpx.Request("GET", "http://core/vault/check"))
        )
        out = await core_gateway.call_core_check(user_id="u1", core_url="http://core", api_key="k")

    assert "2/3" in out
    assert "notes/b.md" in out
    assert "missing _schema" in out


async def test_call_core_check_transport_error_returns_friendly_string():
    with patch("core_gateway.httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = _mock_get_client(exc=httpx.ConnectError("boom"))
        out = await core_gateway.call_core_check(user_id="u1", core_url="http://core", api_key="k")

    assert "failed" in out.lower()
    assert "boom" in out

"""Direct tests for core_gateway seam."""

from unittest.mock import AsyncMock, patch

import httpx

import core_gateway


def _mock_sentinel_client(return_value=None, exc=None):
    """Build a mock sentinel_client whose post_to_module() returns/raises as configured."""
    client = AsyncMock()
    if exc is not None:
        client.post_to_module = AsyncMock(side_effect=exc)
    else:
        client.post_to_module = AsyncMock(return_value=return_value)
    return client


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


# --- call_core_pipeline_start / call_core_pipeline_status (Phase 46-07) ---


async def test_call_core_pipeline_start_posts_and_formats_response():
    client = _mock_sentinel_client(return_value={"pipeline_id": "2026-07-06T00:00:00Z", "status": "running", "mode": "pipeline"})
    out = await core_gateway.call_core_pipeline_start(user_id="u1", mode="pipeline", sentinel_client=client)

    client.post_to_module.assert_awaited_once()
    call_args = client.post_to_module.await_args
    assert call_args.args[0] == "vault/pipeline/start"
    assert call_args.args[1] == {"user_id": "u1", "mode": "pipeline"}
    assert "2026-07-06T00:00:00Z" in out
    assert "pipeline" in out
    assert "status" in out.lower()


async def test_call_core_pipeline_start_transport_error_returns_friendly_string():
    client = _mock_sentinel_client(exc=httpx.ConnectError("boom"))
    out = await core_gateway.call_core_pipeline_start(user_id="u1", mode="ralph", sentinel_client=client)

    assert "failed" in out.lower()
    assert "boom" in out


async def test_call_core_pipeline_start_blocked_surfaces_concurrency_message():
    client = _mock_sentinel_client(return_value={"pipeline_id": None, "status": "blocked", "mode": "pipeline"})
    out = await core_gateway.call_core_pipeline_start(user_id="u1", mode="pipeline", sentinel_client=client)

    assert "already in progress" in out.lower()


async def test_call_core_pipeline_status_formats_per_phase_counts():
    body = {
        "pipeline_id": "2026-07-06T00:00:00Z",
        "status": "complete",
        "mode": "pipeline",
        "entries_total": 5,
        "entries_processed": 5,
        "reduced": 4,
        "hubs_touched": 2,
        "reweave_edits": 1,
        "verify_failed": 1,
        "verify_requeued": 1,
        "errors": [],
    }
    with patch("core_gateway.httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = _mock_get_client(
            response=httpx.Response(200, json=body, request=httpx.Request("GET", "http://core/vault/pipeline/status"))
        )
        out = await core_gateway.call_core_pipeline_status(user_id="u1", core_url="http://core", api_key="k")

    assert "complete" in out
    assert "pipeline" in out
    assert "5/5" in out or ("5" in out and "5" in out)
    assert "reduced=4" in out
    assert "hubs_touched=2" in out
    assert "reweave_edits=1" in out
    assert "verify_failed=1" in out
    assert "verify_requeued=1" in out


async def test_call_core_pipeline_status_transport_error_returns_friendly_string():
    with patch("core_gateway.httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = _mock_get_client(exc=httpx.ConnectError("boom"))
        out = await core_gateway.call_core_pipeline_status(user_id="u1", core_url="http://core", api_key="k")

    assert "failed" in out.lower()
    assert "boom" in out


# --- call_core_migrate_start / call_core_migrate_status (Phase 47-05) ---


async def test_call_core_migrate_start_posts_and_formats_dry_run_response():
    client = _mock_sentinel_client(return_value={"migration_id": "2026-07-06T00:00:00Z", "status": "running", "mode": "dry_run"})
    out = await core_gateway.call_core_migrate_start(user_id="u1", dry_run=True, sentinel_client=client)

    client.post_to_module.assert_awaited_once()
    call_args = client.post_to_module.await_args
    assert call_args.args[0] == "vault/migrate/start"
    assert call_args.args[1] == {"user_id": "u1", "dry_run": True}
    assert "2026-07-06T00:00:00Z" in out
    assert "dry-run" in out.lower()


async def test_call_core_migrate_start_posts_live_response():
    client = _mock_sentinel_client(return_value={"migration_id": "2026-07-06T00:00:00Z", "status": "running", "mode": "live"})
    out = await core_gateway.call_core_migrate_start(user_id="u1", dry_run=False, sentinel_client=client)

    call_args = client.post_to_module.await_args
    assert call_args.args[1] == {"user_id": "u1", "dry_run": False}
    assert "2026-07-06T00:00:00Z" in out
    assert "dry-run" not in out.lower()


async def test_call_core_migrate_start_transport_error_returns_friendly_string():
    client = _mock_sentinel_client(exc=httpx.ConnectError("boom"))
    out = await core_gateway.call_core_migrate_start(user_id="u1", dry_run=True, sentinel_client=client)

    assert "failed" in out.lower()
    assert "boom" in out


async def test_call_core_migrate_status_formats_report_fields():
    body = {
        "migration_id": "2026-07-06T00:00:00Z",
        "status": "complete",
        "mode": "dry_run",
        "dry_run": True,
        "planned_moves": [],
        "ops_moved": [{"src": "journal/a.md", "dst": "ops/journal/2026-07-06/a.md"}],
        "notes_backfilled": 3,
        "verify_failed": 1,
        "new_orphans": 0,
        "rolled_back": False,
        "errors": [],
    }
    with patch("core_gateway.httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = _mock_get_client(
            response=httpx.Response(200, json=body, request=httpx.Request("GET", "http://core/vault/migrate/status"))
        )
        out = await core_gateway.call_core_migrate_status(user_id="u1", core_url="http://core", api_key="k")

    assert "complete" in out
    assert "dry_run" in out
    assert "ops_moved=1" in out
    assert "notes_backfilled=3" in out
    assert "verify_failed=1" in out
    assert "new_orphans=0" in out
    assert "rolled_back=False" in out


async def test_call_core_migrate_status_transport_error_returns_friendly_string():
    with patch("core_gateway.httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = _mock_get_client(exc=httpx.ConnectError("boom"))
        out = await core_gateway.call_core_migrate_status(user_id="u1", core_url="http://core", api_key="k")

    assert "failed" in out.lower()
    assert "boom" in out


async def test_call_core_pipeline_status_blocked_surfaces_concurrency_message():
    body = {
        "pipeline_id": "2026-07-06T00:00:00Z",
        "status": "blocked",
        "mode": "pipeline",
        "entries_total": 0,
        "entries_processed": 0,
        "reduced": 0,
        "hubs_touched": 0,
        "reweave_edits": 0,
        "verify_failed": 0,
        "verify_requeued": 0,
        "errors": [],
    }
    with patch("core_gateway.httpx") as mock_httpx:
        mock_httpx.AsyncClient.return_value = _mock_get_client(
            response=httpx.Response(200, json=body, request=httpx.Request("GET", "http://core/vault/pipeline/status"))
        )
        out = await core_gateway.call_core_pipeline_status(user_id="u1", core_url="http://core", api_key="k")

    assert "already in progress" in out.lower()

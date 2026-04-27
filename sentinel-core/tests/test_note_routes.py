"""Tests for /note/classify and /inbox routes (260427-vl1 Tasks 5 + 6).

Uses FastAPI TestClient with a fake in-memory ObsidianClient and the
classifier patched via monkeypatch / unittest.mock.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.note import router as note_router
from app.services.note_classifier import ClassificationResult


class FakeObsidian:
    """In-memory Obsidian stand-in. Tests inspect `.store` directly."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []

    async def read_note(self, path: str) -> str:
        self.calls.append(("read", path))
        return self.store.get(path, "")

    async def write_note(self, path: str, body: str) -> None:
        self.calls.append(("write", path))
        self.store[path] = body

    async def delete_note(self, path: str) -> None:
        self.calls.append(("delete", path))
        self.store.pop(path, None)


def _make_app(obsidian: FakeObsidian) -> FastAPI:
    app = FastAPI()
    app.state.obsidian_client = obsidian
    app.include_router(note_router)
    return app


# --- POST /note/classify ---


def test_classify_filed_high_conf():
    obsidian = FakeObsidian()
    fake_result = ClassificationResult(
        topic="reference",
        confidence=0.9,
        title_slug="some-fact",
        reasoning="discrete fact",
    )
    with patch(
        "app.routes.note.classify_note", new=AsyncMock(return_value=fake_result)
    ):
        client = TestClient(_make_app(obsidian))
        resp = client.post("/note/classify", json={"content": "Pi is 3.14159", "topic": None})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["action"] == "filed"
    assert data["topic"] == "reference"
    assert data["path"].startswith("references/some-fact-")
    # Verify write_note called once with full frontmatter
    write_paths = [p for kind, p in obsidian.calls if kind == "write"]
    assert len(write_paths) == 1
    written = obsidian.store[write_paths[0]]
    assert "topic: reference" in written
    assert "title_slug: some-fact" in written
    assert "source: note-import" in written


def test_classify_dropped_noise():
    obsidian = FakeObsidian()
    fake_result = ClassificationResult(
        topic="noise", confidence=1.0, title_slug="x", reasoning="r"
    )
    with patch(
        "app.routes.note.classify_note", new=AsyncMock(return_value=fake_result)
    ):
        client = TestClient(_make_app(obsidian))
        resp = client.post("/note/classify", json={"content": "hello", "topic": None})
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "dropped"
    assert data["reason"] == "cheap-filter:noise"
    # write_note never called
    assert not [c for c in obsidian.calls if c[0] == "write"]


def test_classify_inboxed_low_conf():
    obsidian = FakeObsidian()
    fake_result = ClassificationResult(
        topic="unsure", confidence=0.3, title_slug="x", reasoning="dunno"
    )
    with patch(
        "app.routes.note.classify_note", new=AsyncMock(return_value=fake_result)
    ):
        client = TestClient(_make_app(obsidian))
        resp = client.post("/note/classify", json={"content": "ambiguous", "topic": None})
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "inboxed"
    # Inbox file was written
    assert "inbox/_pending-classification.md" in obsidian.store
    body = obsidian.store["inbox/_pending-classification.md"]
    assert "## Entry 1" in body
    assert "ambiguous" in body


def test_classify_explicit_user_topic_files_to_correct_dir():
    obsidian = FakeObsidian()
    # When user_topic="learning" is passed, classifier returns conf=1.0 / topic=learning
    fake_result = ClassificationResult(
        topic="learning",
        confidence=1.0,
        title_slug="finished-course",
        reasoning="explicit",
    )
    with patch(
        "app.routes.note.classify_note", new=AsyncMock(return_value=fake_result)
    ) as mock_classifier:
        client = TestClient(_make_app(obsidian))
        resp = client.post(
            "/note/classify", json={"content": "Finished course", "topic": "learning"}
        )
    assert resp.status_code == 200
    assert resp.json()["action"] == "filed"
    assert resp.json()["path"].startswith("learning/finished-course-")
    # user_topic flowed through
    call_kwargs = mock_classifier.await_args.kwargs
    if "user_topic" in call_kwargs:
        assert call_kwargs["user_topic"] == "learning"
    else:
        assert mock_classifier.await_args.args[1] == "learning"


# --- GET /inbox ---


def test_get_inbox_empty():
    obsidian = FakeObsidian()
    client = TestClient(_make_app(obsidian))
    resp = client.get("/inbox")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entries"] == []
    assert data["rendered"] == "(inbox is empty)"


def test_get_inbox_two_entries():
    obsidian = FakeObsidian()
    # Seed via append_entry
    from app.services.inbox import append_entry, build_initial_inbox

    body = build_initial_inbox()
    body = append_entry(
        body,
        "first candidate text",
        ClassificationResult(topic="unsure", confidence=0.4, title_slug="x", reasoning="r"),
        suggested=["reference"],
    )
    body = append_entry(
        body,
        "second candidate text",
        ClassificationResult(topic="unsure", confidence=0.3, title_slug="y", reasoning="s"),
        suggested=["journal"],
    )
    obsidian.store["inbox/_pending-classification.md"] = body

    client = TestClient(_make_app(obsidian))
    resp = client.get("/inbox")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entries"]) == 2
    assert "first candidate text" in data["rendered"]
    assert "(suggested: reference)" in data["rendered"]


# --- POST /inbox/classify ---


def test_inbox_classify_files_and_removes():
    obsidian = FakeObsidian()
    from app.services.inbox import append_entry, build_initial_inbox

    body = build_initial_inbox()
    body = append_entry(
        body,
        "Pi is 3.14159 — useful constant",
        ClassificationResult(topic="unsure", confidence=0.4, title_slug="x", reasoning="r"),
    )
    obsidian.store["inbox/_pending-classification.md"] = body

    fake_result = ClassificationResult(
        topic="reference",
        confidence=1.0,
        title_slug="pi-constant",
        reasoning="explicit",
    )
    with patch(
        "app.routes.note.classify_note", new=AsyncMock(return_value=fake_result)
    ):
        client = TestClient(_make_app(obsidian))
        resp = client.post(
            "/inbox/classify", json={"entry_n": 1, "topic": "reference"}
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["action"] == "filed"
    assert data["path"].startswith("references/pi-constant-")
    # Inbox now empty (entry removed)
    from app.services.inbox import parse_inbox

    assert parse_inbox(obsidian.store["inbox/_pending-classification.md"]) == []


def test_inbox_classify_404_on_missing_entry():
    obsidian = FakeObsidian()
    from app.services.inbox import build_initial_inbox

    obsidian.store["inbox/_pending-classification.md"] = build_initial_inbox()
    client = TestClient(_make_app(obsidian))
    resp = client.post("/inbox/classify", json={"entry_n": 99, "topic": "reference"})
    assert resp.status_code == 404


# --- POST /inbox/discard ---


def test_inbox_discard_removes_entry():
    obsidian = FakeObsidian()
    from app.services.inbox import append_entry, build_initial_inbox, parse_inbox

    body = build_initial_inbox()
    body = append_entry(
        body,
        "first",
        ClassificationResult(topic="unsure", confidence=0.4, title_slug="x", reasoning="r"),
    )
    body = append_entry(
        body,
        "second",
        ClassificationResult(topic="unsure", confidence=0.3, title_slug="y", reasoning="s"),
    )
    obsidian.store["inbox/_pending-classification.md"] = body

    client = TestClient(_make_app(obsidian))
    resp = client.post("/inbox/discard", json={"entry_n": 1})
    assert resp.status_code == 200
    assert resp.json()["action"] == "discarded"
    after = parse_inbox(obsidian.store["inbox/_pending-classification.md"])
    assert len(after) == 1
    assert after[0].candidate_text == "second"
    assert after[0].entry_n == 1  # renumbered

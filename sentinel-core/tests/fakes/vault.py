"""In-memory ``FakeVault`` — the canonical test double for the Vault seam.

Implements the full ``app.vault.Vault`` Protocol against a ``dict[str, str]``
backing store (path → body). Every method preserves the contract of the
production ``ObsidianVault`` adapter at the observable level — same return
shapes, same graceful-degrade vs raise semantics — so tests that swap
``MagicMock(spec=ObsidianClient)`` for ``FakeVault()`` are pure
fixture-wiring refactors (Test-Rewrite Ban allowed list): assertions and
call paths stay identical.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.vault import VaultUnreachableError

# Re-use the canonical sweep method bodies from ObsidianVault — they only
# touch read_note / write_note / delete_note, so they work against any
# Vault-shaped store. This keeps the FakeVault's trash/relocate/lock
# semantics byte-identical to production without duplicating logic.
from app.vault import ObsidianVault as _ObsidianVault

_LOCKFILE_PATH = "ops/sweeps/_in-progress.md"


class FakeVault:
    """Dict-backed Vault implementation for tests.

    Pre-populate via the public ``notes`` and ``dirs`` attributes:

        v = FakeVault()
        v.notes["self/identity.md"] = "# I am ..."
        v.dirs[""] = ["self/", "ops/"]
        v.dirs["self"] = ["identity.md"]

    Or via the convenience kwargs:

        v = FakeVault(
            notes={"self/identity.md": "# I am ..."},
            dirs={"": ["self/"], "self": ["identity.md"]},
        )

    Pass ``raise_unreachable=True`` to flip ``read_persona`` (and any
    capability that should distinguish transport failure) into the
    ``VaultUnreachableError`` branch.
    """

    def __init__(
        self,
        *,
        notes: dict[str, str] | None = None,
        dirs: dict[str, list[str]] | None = None,
        raise_unreachable: bool = False,
    ) -> None:
        self.notes: dict[str, str] = dict(notes or {})
        self.dirs: dict[str, list[str]] = dict(dirs or {})
        self.raise_unreachable: bool = raise_unreachable
        self._lock_acquired: bool = False
        self._lock_started_at: datetime | None = None

    @property
    def store(self) -> dict[str, str]:
        """Alias for ``notes`` — preserves call-site compatibility with the
        legacy ``FakeObsidian`` used by test_vault_sweeper before the seam
        consolidation. Mutating ``v.store[path] = body`` mutates ``notes``
        because it is the same dict object."""
        return self.notes

    # --- Health / persona ---

    async def check_health(self) -> bool:
        return not self.raise_unreachable

    async def read_persona(self) -> str | None:
        if self.raise_unreachable:
            raise VaultUnreachableError("FakeVault simulated transport failure")
        return self.notes.get("sentinel/persona.md")

    # --- Self-context / sessions ---

    async def get_user_context(self, user_id: str) -> str | None:
        # Single-user system per D-01 — the user_id is not used to key the
        # identity file in production, so it isn't here either.
        return self.notes.get("self/identity.md")

    async def read_self_context(self, path: str) -> str:
        return self.notes.get(path, "")

    async def get_recent_sessions(self, user_id: str, limit: int = 3) -> list[str]:
        # Return any pre-populated session bodies whose key matches the
        # user_id substring rule from production (``f"{user_id}-" in name``).
        candidates: list[tuple[str, str]] = []
        for path, body in self.notes.items():
            if not path.startswith("ops/sessions/"):
                continue
            filename = path.rsplit("/", 1)[-1]
            if f"{user_id}-" in filename and filename.endswith(".md"):
                candidates.append((path, body))
        candidates.sort(key=lambda t: t[0], reverse=True)
        return [b for _, b in candidates[:limit]]

    # Domain-language alias — production exposes both names so callers can
    # use whichever reads best at the call site.
    read_recent_sessions = get_recent_sessions

    async def write_session_summary(self, path: str, content: str) -> None:
        # Swallow-on-failure semantics: pre-populating with raise_unreachable
        # should still return None (not raise) per the production contract.
        if self.raise_unreachable:
            return None
        self.notes[path] = content
        return None

    # --- Search / listing / primitives ---

    async def find(self, query: str) -> list[dict]:
        results: list[dict] = []
        for path, body in self.notes.items():
            if query.lower() in body.lower():
                results.append({"filename": path, "score": 1.0})
        return results

    # Accept the historical name too — some callers may still pass it
    # through during the transition; production drops the alias in task 5.
    search_vault = find

    async def list_under(self, prefix: str = "") -> list[str]:
        return list(self.dirs.get(prefix, []))

    # Historical alias for the same reason as ``search_vault``.
    list_directory = list_under

    async def read_note(self, path: str) -> str:
        return self.notes.get(path, "")

    async def write_note(self, path: str, body: str) -> None:
        self.notes[path] = body

    async def delete_note(self, path: str) -> None:
        self.notes.pop(path, None)

    async def patch_append(self, path: str, body: str) -> None:
        self.notes[path] = self.notes.get(path, "") + body

    # --- Sweep capabilities ---
    #
    # Delegate to the canonical ObsidianVault method bodies — they only
    # operate against read_note/write_note/delete_note, so they work
    # unchanged against FakeVault's in-memory store. Mirroring the
    # production logic keeps observable behavior byte-identical.

    async def move_to_trash(
        self,
        path: str,
        when: datetime | None = None,
        *,
        reason: str = "",
        sweep_at: str | None = None,
    ) -> str:
        return await _ObsidianVault.move_to_trash(
            self, path, when, reason=reason, sweep_at=sweep_at
        )

    async def relocate(
        self,
        src: str,
        dst: str,
        *,
        sweep_at: str | None = None,
    ) -> str:
        return await _ObsidianVault.relocate(self, src, dst, sweep_at=sweep_at)

    async def acquire_sweep_lock(self, now: datetime | None = None) -> bool:
        return await _ObsidianVault.acquire_sweep_lock(self, now)

    async def release_sweep_lock(self) -> None:
        return await _ObsidianVault.release_sweep_lock(self)

    # --- Test-only helpers ---

    def assert_note_at(self, path: str, contains: str) -> None:
        """Convenience for assert-style tests: raises AssertionError with a
        useful message if the note at ``path`` doesn't contain ``contains``.
        """
        body = self.notes.get(path, "")
        assert contains in body, (
            f"FakeVault note at {path!r} does not contain {contains!r}; "
            f"actual body: {body!r}"
        )

    def __contains__(self, path: str) -> bool:
        return path in self.notes

    def __getitem__(self, path: str) -> str:
        return self.notes[path]

    # Iterator over all stored note paths — handy for snapshot diffing.
    def __iter__(self) -> Any:
        return iter(self.notes)

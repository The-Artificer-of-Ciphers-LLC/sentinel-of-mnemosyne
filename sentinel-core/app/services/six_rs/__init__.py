"""The 6 Rs pipeline stage modules (Phase 46).

Record -> Reduce -> Reflect -> Reweave -> Verify -> Rethink. Record already
ships (``note_intake.py`` / ``inbox.py``, PIPE-01); this package holds the
five stage modules Phase 46 adds: ``reduce``, ``reflect``, ``reweave``,
``verify``, ``rethink`` -- each an independent structured LLM completion
(ARCHITECTURE.md Pattern 1, CONTEXT.md D-05). This ``__init__.py`` is an
empty package marker only, added in Wave 0 (Plan 46-01) so both Wave-2
stage plans can add modules here without an ``__init__.py`` ownership
conflict.
"""
from __future__ import annotations

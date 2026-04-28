# Deferred items — 260427-cui

These tests were failing on `main` before this task started and are out of
scope for the cartosia → ingest refactor:

- `modules/pathfinder/tests/test_foundry.py::test_roll_event_accepted` — NameError: `get_profile`
- `modules/pathfinder/tests/test_foundry.py::test_notify_dispatched` — NameError: `get_profile`
- `modules/pathfinder/tests/test_foundry.py::test_llm_fallback` — NameError: `get_profile`
- `modules/pathfinder/tests/test_registration.py::test_registration_payload_has_16_routes` — payload has grown to 19 routes; assertion still pins 16.

Both were verified pre-existing via `git stash; pytest; git stash pop`.

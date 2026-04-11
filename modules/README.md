# Sentinel Modules

This directory is the future home for Sentinel extension modules (Pathfinder 2e, Music Lesson, Finance, Trading, Coder).

## Module Contract

Each module lives in its own subdirectory and provides:
- `compose.yml` — Docker Compose service definition with `profiles: ["<module-name>"]`
- `README.md` — Module-specific setup and usage

See `docs/MODULE-SPEC.md` for the full module authoring specification.

## Status

Modules are scheduled for Phase 11+ development. The module contract is defined but no modules are implemented yet.

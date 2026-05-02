# ADR-0002 — Vault Seam Lives at `app/vault.py`, Not Under `app/clients/`

**Status:** accepted
**Date:** 2026-05-02
**Plan:** `.planning/quick/260502-cky-vault-capability-seam-introduce-vault-pr/`
**Supersedes:** none
**Related:** ADR-0001 (Sentinel persona source).

## Decision

The `Vault` Protocol and the concrete `ObsidianVault` adapter live in
`sentinel-core/app/vault.py`, **not** in `sentinel-core/app/clients/`.

`app/clients/` continues to host single-purpose external HTTP adapters
(`litellm_provider.py`, `pi_adapter.py`, `embeddings.py`,
`anthropic_registry.py`) — adapters that fulfil one technical role each
and that have no shared domain language with the rest of the codebase.

The Vault is intentionally **not** placed there. It is a single,
top-level capability seam.

## Rationale

The Vault is a *capability seam* in the domain language used throughout
PROJECT.md, CONTEXT.md, and the operator-facing artefacts. The vocabulary
of the system is "vault", "persona", "self-context", "session summary",
"trash", "topic folder" — domain concepts that live above the HTTP layer.
The Obsidian Local REST API is one possible backing for these
capabilities; future backings (a different vault implementation, a
cached/projected store, a write-through buffer) would still implement the
same Protocol and would still be referenced as "the vault" by every
caller.

Co-locating the Protocol and the canonical adapter in a single top-level
module — `app/vault.py` — surfaces the seam at the module hierarchy. A
reader scanning `sentinel-core/app/` immediately sees `vault.py` and
understands that the Vault is a first-class concept of the system, not
one of N HTTP adapters. By contrast, `app/clients/obsidian_vault.py`
would frame the seam as an implementation detail of the Obsidian
integration, encouraging future contributors to reach past the Protocol
and program against the adapter directly.

The Vault also owns capabilities that have no analogue in the other
clients — `read_persona()` distinguishing 404 from transport failure
(ADR-0001), the lockfile semantics for `acquire_sweep_lock` /
`release_sweep_lock`, the `move_to_trash` / `relocate` orchestration that
absorbs frontmatter provenance recording. None of these are HTTP
plumbing; they are vault-shaped contracts.

## Operator Pre-Authorization

Round-2 architecture review for plan `260502-cky` posed Q4: should the
Vault Protocol and the `ObsidianVault` adapter live in a single top-level
file, or follow the existing `app/clients/` convention?

The operator selected **(a) Single file** with full awareness that this
breaks the `app/clients/` convention. The decision is recorded in the
plan's "Decisions (locked)" table and is durably captured here so that a
future architecture pass cannot silently undo it.

## Consequence

- Future readers who notice `app/clients/obsidian_*.py` analogues and ask
  "should `vault.py` move under `clients/`?" must read this ADR first.
  The answer is **no**.

- A new vault backing (in-memory cache, alternate store, projection
  layer) becomes a peer of `ObsidianVault` inside `app/vault.py`, or a
  separate file imported into `app/vault.py`. It does **not** live under
  `app/clients/`.

- Other top-level capability seams that emerge with the same shape
  (single Protocol with a small set of canonical adapters expressing
  domain capabilities, not raw HTTP plumbing) should follow this pattern:
  `app/<seam>.py`, sibling to `app/vault.py`.

- The `app/clients/` directory remains the home for narrow,
  single-purpose external HTTP adapters that have no domain-level
  Protocol seam. New entries there should be one-file adapters with no
  associated domain capability vocabulary.

## Notes

- The migration plan `260502-cky` introduced this layout in six atomic
  commits. Task 1 created `app/vault.py` and a transitional shim at
  `app/clients/obsidian.py`; task 5 deleted the shim. Task 6 (this ADR)
  records the convention break.
- ADR-0001 ("Sentinel persona source") describes the startup contract
  the Vault seam preserves end-to-end via `read_persona()` and the
  typed `VaultUnreachableError` exception. The two ADRs read together as
  a pair — ADR-0001 sets the contract, ADR-0002 explains where the
  contract's implementation lives.

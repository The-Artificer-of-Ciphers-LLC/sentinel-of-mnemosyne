# Pathfinder Module Extraction + GitHub Presentation Plan

## Objective
Split Pathfinder into its own repository with independent releases, while presenting the Sentinel ecosystem on GitHub as a cohesive product (not a flat repo list).

## Target End State
- `sentinel-core` repo (core runtime)
- `sentinel-module-pathfinder` repo (PF2E module, versioned independently)
- Optional `sentinel-shared-sdk` repo/package (shared contracts/types)
- One ecosystem landing surface on GitHub that groups everything visually and operationally

---

## Phase 0 — Prepare contracts (in current mono-repo)
1. Freeze and document module runtime contract:
   - `/modules/register` payload
   - auth header behavior (`X-Sentinel-Key`)
   - proxy request/response/error shapes
2. Identify shared code used by Pathfinder and Core.
3. Add contract tests in both sides before extraction.

Deliverable: `docs/contracts/module-runtime-contract.md` + passing contract tests.

---

## Phase 1 — Extract Pathfinder to new repo
1. Create new repo: `sentinel-module-pathfinder`.
2. Move code:
   - `modules/pathfinder/**`
   - relevant docs (`docs/foundry-setup.md` sections or split docs)
3. Preserve git history using subtree filter (recommended) or `git filter-repo`.
4. Add standalone CI:
   - tests, lint, image build, release workflow
5. Publish module image independently:
   - `ghcr.io/<org>/sentinel-module-pathfinder:<tag>`

Deliverable: Pathfinder runs and releases from its own repo.

---

## Phase 2 — Wire core to external module artifact
1. Update core deployment docs/compose samples to reference Pathfinder image tags.
2. Pin module version in deploy examples (no implicit latest for production docs).
3. Add compatibility matrix:
   - Sentinel Core version ↔ Pathfinder module version

Deliverable: Core can consume Pathfinder as external, versioned module.

---

## Phase 3 — Shared code strategy
Choose one:
- **A. Keep small duplication** (fastest initially)
- **B. Publish shared package** (`sentinel-shared-sdk`)

Recommended: start with A, move to B only when churn/duplication becomes costly.

Deliverable: explicit policy documented in both repos.

---

## Phase 4 — Versioning and release policy
- Sentinel Core stays on its own line (e.g., `v0.5x`).
- Pathfinder module uses independent semver (now `v1.x`).
- Every Pathfinder release notes:
  - required minimum core version
  - breaking contract changes

Deliverable: Release template in Pathfinder repo.

---

## GitHub “grouped ecosystem” presentation (non-boring)

## 1) Use a GitHub Organization + Profile README as product homepage
Create/update org profile repo `.github` with `profile/README.md` containing:
- Product overview diagram
- “Start here” quick links
- Module cards (Core, Pathfinder, future modules)
- Compatibility matrix snippet
- Roadmap board link

This becomes the visual landing page for the whole ecosystem.

## 2) Use a GitHub Project (table + board + roadmap views)
Create one org-level Project: **Sentinel Ecosystem Roadmap**
- Group items by repo/module
- Views:
  - Board by status
  - Table by module
  - Timeline by target release

## 3) Add pinned repositories + topic taxonomy
- Pin: `sentinel-core`, `sentinel-module-pathfinder`, `sentinel-shared-sdk` (if used), `sentinel-deploy`.
- Standard topics across repos:
  - `sentinel-ecosystem`
  - `sentinel-module`
  - `pathfinder2e`
  - `obsidian`
  - `fastapi`

## 4) Add architecture map repo (optional but high value)
Create `sentinel-ecosystem` repo containing:
- ecosystem docs
- diagrams
- compatibility matrix
- ADR index across repos

This gives one canonical “map” instead of making users click random repos.

## 5) Use Releases + package links consistently
In each repo:
- Release notes include links to dependent repos/releases.
- README includes “Works with” section.
- GHCR package description links back to ecosystem homepage.

---

## Migration checklist (execution order)
1. Contract docs + tests complete.
2. Create Pathfinder repo and move code/history.
3. Standalone CI green in Pathfinder repo.
4. Publish first independent Pathfinder `v1.x` release.
5. Update core deploy docs to external module image/tag.
6. Publish compatibility matrix.
7. Launch org profile landing page + project board + pinned repos.

---

## Risks and mitigations
- **Contract drift** between core and module
  - Mitigation: shared contract tests + compatibility matrix.
- **Release confusion** from independent versions
  - Mitigation: explicit “Works with Core >=X.Y” in every Pathfinder release.
- **Discoverability fragmentation**
  - Mitigation: org profile homepage + ecosystem repo + pinned repos/topics.

---

## Recommended immediate next step
Implement **Phase 0** first (contract freeze + tests), then perform extraction in one controlled cutover window.
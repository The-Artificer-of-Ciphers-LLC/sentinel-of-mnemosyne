---
type: research
quick_id: 260708-mz4
task: "Assess whether the Open Knowledge Format (OKF) should be incorporated into Sentinel"
date: 2026-07-08
source_url: https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing
recommendation: do-not-incorporate-now
---

# OKF Incorporation Assessment

**Question:** Does the Open Knowledge Format (OKF) — from Google Cloud's "how the Open Knowledge Format can improve data sharing" — need to be incorporated into Sentinel of Mnemosyne?

**Answer: No — not now.** But the finding is more interesting than a flat "no": OKF is a near-exact formalization of the pattern Sentinel *already implements*. The recommendation is therefore "don't adopt as a native format; treat it as validation of the current design, and revisit a small **export adapter** only if OKF matures past draft and a concrete consumer appears."

---

## 1. What OKF actually is (the surprise)

OKF is **not** RDF, JSON-LD, triples, a property graph, or a binary serialization. Per Google's own spec ([SPEC.md](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)):

> "OKF v0.1 represents knowledge as a directory of markdown files with YAML frontmatter, with a small set of agreed-upon conventions."

- **Container:** a "bundle" = a directory of `.md` files. No single-file format, no MIME type declared.
- **Required frontmatter:** exactly **one** field — `type` (a producer-defined string). Recommended: `title`, `description`, `resource` (URI), `tags`, `timestamp`.
- **Concept identity** = file path minus `.md` (`tables/orders.md` → `tables/orders`).
- **Edges** = ordinary markdown links (`[customers](/tables/customers.md)`); consumers **must tolerate broken links**.
- **Reserved files:** `index.md` (progressive-disclosure directory listing) and `log.md` (chronological change history).
- **Explicit design inspiration:** Obsidian vaults / personal wikis and Karpathy's "LLM-wiki" gist. Google is not competing with the semantic web — the spec never mentions RDF/OWL/schema.org.
- **Maturity:** **v0.1, labeled "Draft"**, announced ~2026-06-12, Google-led, no independent standards body. Reference tooling is BigQuery-catalog-shaped (a BigQuery→OKF enrichment agent, an HTML bundle visualizer, sample bundles). Early community tooling exists (`okflint` validator, an `okf-skills` Claude Code plugin) but is *unverified secondary-source* and weeks old.

**Scale verdict:** OKF's *marketing and reference impl* are enterprise/data-warehouse-oriented (BigQuery tables, Knowledge Catalog), but the *format itself* imposes almost no ceremony — one required field, plain markdown, plain directories — so a personal vault conforms with only frontmatter/link normalization.

Sources: [Google Cloud blog](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing) · [okf/SPEC.md](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) · [okf/README.md](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/README.md) · [Knowledge Catalog announcement](https://cloud.google.com/blog/products/data-analytics/introducing-the-google-cloud-knowledge-catalog).

## 2. What Sentinel already is

Sentinel's knowledge layer (verified via graph search of this repo):

- Notes are **markdown files in an Obsidian vault**, written through the Obsidian REST client (`sentinel_shared.ObsidianClientCore`, Phase 48).
- Notes carry **YAML frontmatter** (the `_schema` note-quality contract, Phase 45).
- Relationships are **`[[wikilinks]]`**, with a **zero-orphan graph invariant** enforced by `build_graph_report` / `GraphReport` in `sentinel-core/app/services/graph_analysis.py` and the vendored `shared/sentinel_shared/graph_check.py`.
- Organized by **PARA + per-module namespaces** (`notes/`, `pf2e/`, `music/`), with **hub/index notes** (the 4-note hub-mesh seed in Phase 48 is exactly an `index.md`-style progressive-disclosure hub).
- Purpose: a **single-user personal AI memory** — a Discord/interface conversation goes in, curated knowledge gets written to Obsidian so the next conversation starts smarter.

## 3. OKF ↔ Sentinel mapping

| OKF v0.1 | Sentinel today | Gap |
|---|---|---|
| Directory of `.md` files | Markdown notes in Obsidian vault | none |
| YAML frontmatter | `_schema` frontmatter | none (structural) |
| Required `type:` field | `_schema` fields; no guaranteed `type:` | small — add/standardize a `type` |
| `index.md` progressive disclosure | Hub/index notes | none (naming only) |
| `log.md` change history | git history + session diary | optional |
| Edges = **standard markdown links** | Edges = **`[[wikilinks]]`** | **the one real mechanical difference** |
| Purpose: cross-vendor/agent **data sharing** | Purpose: **single-user** memory | the value gap |

Structurally Sentinel is ~90% OKF-conformant already. The convergence is the headline: Google independently arrived at the same "markdown vault as agent-consumable knowledge" architecture Sentinel has been building.

## 4. Why NOT to incorporate it now

1. **No data-sharing need.** OKF's entire value proposition is *portability across vendors/agents/catalogs*. Sentinel is single-user; there is no external OKF consumer today. Adopting an interop standard with no counterparty is cost without benefit.
2. **It's a v0.1 draft.** Google-led, no standards body, weeks old, explicitly "a starting point, not a finished standard." Retrofitting a mature system to a draft spec is premature (choose-boring-technology / Gall's Law). The breaking-change surface is real (major-version = breaking).
3. **The one required change would *degrade* Sentinel.** Converting `[[wikilinks]]` → plain markdown links to satisfy OKF's link convention would break Obsidian's graph view, backlinks, and autocomplete — the native UX and the substrate of Sentinel's zero-orphan invariant — for **zero** current gain. OKF consumers are told to tolerate non-conforming links anyway.
4. **Sentinel already has a working, hard-won schema.** `_schema` + PARA + zero-orphan + the shared vault client are the product of many phases. OKF adds no capability Sentinel lacks.

## 5. If it's ever worth doing: an export adapter, not a migration

The correct shape of any future OKF work is an **optional, additive export adapter** — `vault → OKF bundle` — that:
- reads the existing vault (native `[[wikilinks]]` untouched),
- emits an OKF bundle (rewrite links to relative markdown, ensure a `type:` per note, synthesize `index.md`/`log.md`), 
- lives in `sentinel_shared` (both Core and modules could emit their namespace as a bundle),
- costs roughly a small script (pyyaml + a wikilink→mdlink pass; no off-the-shelf Google parser exists yet).

This preserves Sentinel's Obsidian-native model while producing OKF on demand. **Trigger conditions to revisit:** (a) OKF ships past v0.1 draft / gets multi-vendor governance, AND (b) a concrete consumer exists (e.g. wanting to hand a module's knowledge to an external OKF-aware agent, or publish a module vault).

## 6. Recommendation

- **Do not incorporate OKF now.** No native-format change, no dependency, no phase.
- **Record the convergence as design validation** — OKF independently confirms Sentinel's "markdown vault as agent memory" bet.
- **Backlog (not scheduled):** a `sentinel_shared` OKF **export adapter**, gated on OKF maturity + a real consumer. Small, additive, non-breaking when it happens.
- Optional cheap hygiene, independent of OKF: consider whether a standardized `type:` in `_schema` frontmatter is worth adding on its own merits (it aligns with OKF for free if OKF ever matters) — but only if it earns its keep for Sentinel's own recall/retrieval, not to chase the spec.

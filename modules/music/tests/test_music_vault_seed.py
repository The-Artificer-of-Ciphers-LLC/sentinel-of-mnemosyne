"""Pure module-side compliance test for the music/ hub-mesh seed (MUS-05, D-08/D-10).

Proves — with NO live Obsidian connection and NO sentinel-core import — that
HUB_NOTES is zero-orphan under the vendored ``sentinel_shared.graph_check``
rule and that every note carries a trailing ```_schema fenced block plus at
least one wikilink. This is the module-side compliance gate D-10 requires,
since Core's own ``:graph``/``:check`` walk is hard-scoped to
``NOTES_ROOT="notes"`` and cannot see ``music/``.
"""
from app.seed import HUB_NOTES
from sentinel_shared.graph_check import build_graph_report, extract_wikilinks


def test_hub_mesh_is_zero_orphan() -> None:
    """build_graph_report over the 4-note HUB_NOTES map returns .orphans == []."""
    report = build_graph_report(HUB_NOTES)
    assert report.orphans == []


def test_hub_mesh_has_four_unique_stem_notes() -> None:
    """The mesh has exactly the four mandated unique filename stems."""
    assert len(HUB_NOTES) == 4
    stems = {path.rsplit("/", 1)[-1].removesuffix(".md") for path in HUB_NOTES}
    assert stems == {"index", "lessons-index", "practice-log-index", "ideas-index"}


def test_every_note_has_trailing_schema_block_and_wikilink() -> None:
    """Every note body ends in a ```_schema fence and yields >=1 wikilink."""
    for path, body in HUB_NOTES.items():
        stripped = body.rstrip()
        assert stripped.endswith("```"), f"{path} body must end with the _schema fence"
        assert "```_schema" in body, f"{path} missing a ```_schema block"
        wikilinks = extract_wikilinks(body)
        assert wikilinks, f"{path} has no wikilinks"


def test_schema_block_carries_title_wikilinks_and_null_reserved_fields() -> None:
    """Each note's _schema block carries title + wikilinks + null reserved fields (D-09)."""
    import yaml

    for path, body in HUB_NOTES.items():
        stripped = body.rstrip()
        fence_start = stripped.rindex("```_schema")
        inner = stripped[fence_start + len("```_schema") : -3]
        schema = yaml.safe_load(inner)
        assert isinstance(schema, dict), f"{path} _schema block did not parse to a dict"
        assert "title" in schema, f"{path} _schema missing title"
        assert "wikilinks" in schema, f"{path} _schema missing wikilinks"
        assert schema.get("listenbrainz_context") is None, f"{path} listenbrainz_context not null"
        assert schema.get("discogs_context") is None, f"{path} discogs_context not null"

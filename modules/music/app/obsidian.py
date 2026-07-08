"""ObsidianClient for the music module — pure composition of the shared client
(XMOD-01, D-03/MUS-02).

Core-only: music composes ONLY ObsidianClientCore (get_note/put_note/
list_directory/patch_frontmatter_field). It never composes
ObsidianBinaryMixin or ObsidianHeadingMixin, and it must never import
sentinel-core's Vault Protocol / ObsidianVault (sentinel-core/app/vault.py).
All method bodies live in ``sentinel_shared.obsidian`` — see Plan 48-01.
"""
from sentinel_shared.obsidian import ObsidianClientCore


class ObsidianClient(ObsidianClientCore):
    pass

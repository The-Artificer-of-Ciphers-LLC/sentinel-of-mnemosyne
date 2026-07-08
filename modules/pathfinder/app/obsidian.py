"""ObsidianClient for pathfinder module — pure composition of the shared client (XMOD-01, D-02/D-05).

pf2e no longer owns any client request logic. This file is only a composition
subclass wiring the shared core plumbing together with the two mixins pf2e's
routes/consumers rely on (heading patches + binary token-image storage). All
method bodies live in ``sentinel_shared.obsidian`` — see Plan 48-01/48-02.
"""
from sentinel_shared.obsidian import (
    ObsidianBinaryMixin,
    ObsidianClientCore,
    ObsidianHeadingMixin,
)


class ObsidianClient(ObsidianClientCore, ObsidianBinaryMixin, ObsidianHeadingMixin):
    pass

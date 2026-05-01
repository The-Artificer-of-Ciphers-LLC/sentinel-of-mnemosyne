import discord_internal_notify


def test_resolve_notify_channel_id_prefers_explicit():
    out = discord_internal_notify.resolve_notify_channel_id(7, {1, 2})
    assert out == 7


def test_resolve_notify_channel_id_falls_back_to_min_allowed():
    out = discord_internal_notify.resolve_notify_channel_id(None, {9, 3, 5})
    assert out == 3

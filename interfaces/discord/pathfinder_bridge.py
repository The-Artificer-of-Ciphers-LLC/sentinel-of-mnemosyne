"""Bridge wrapper for Pathfinder command dispatch."""

from __future__ import annotations

import httpx


async def dispatch_pf(
    *,
    args: str,
    user_id: str,
    attachments,
    channel,
    bot_user,
    parse_pf_args,
    dispatch,
    sent_client,
    is_admin,
    valid_relations,
    adapters,
    builders,
):
    parsed, err = parse_pf_args(args)
    if err:
        return err
    assert parsed is not None
    noun, verb, rest, parts = parsed

    async with httpx.AsyncClient() as http_client:
        return await dispatch(
            noun=noun,
            verb=verb,
            rest=rest,
            parts=parts,
            user_id=user_id,
            attachments=attachments,
            channel=channel,
            bot_user=bot_user,
            sentinel_client=sent_client,
            http_client=http_client,
            is_admin=is_admin,
            valid_relations=valid_relations,
            adapters=adapters,
            builders=builders,
        )

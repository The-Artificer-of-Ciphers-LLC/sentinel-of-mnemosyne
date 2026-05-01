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
    map_http_status,
    log_error,
):
    parsed, err = parse_pf_args(args)
    if err:
        return err
    assert parsed is not None
    noun, verb, rest, parts = parsed

    try:
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
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except Exception:
            detail = exc.response.text
        if status not in (404, 409):
            log_error(f"Module returned HTTP {status}: {detail}")
        return map_http_status(status, str(detail))
    except httpx.ConnectError:
        return "Cannot reach the Sentinel. Is sentinel-core running?"
    except httpx.TimeoutException:
        return "The pathfinder module took too long to respond. Try again."
    except Exception as exc:
        log_error(f"Unexpected error in pathfinder dispatch: {exc}")
        return "An unexpected error occurred in pathfinder dispatch."

"""Player interaction orchestrator — onboarding gate + verb dispatch.

Wave 2 slice (plan 37-07): implements the start/style/state surface only.
Subsequent plans extend the verb Literal and add additional `match` arms
(note/ask/npc/todo in plan 08, recall in 09, canonize in 10) — open/closed
extension: never delete a branch, never narrow a return type.

Contract (PVL-01, PVL-05, PVL-06, PVL-07):
  - Slug derivation goes ONLY through identity_adapter (test-injected resolver).
  - Onboarding gate: if profile.md is absent OR `onboarded` != True, every verb
    other than `start` and `style:list` short-circuits to a result with
    requires_onboarding=True. No write adapters are called.
  - Style preset is a closed enum; `style set` with an unknown preset raises
    ValueError listing the four valid presets.

Adapters injected by the route layer:
  obsidian_client    — ObsidianClient (passed through to recall/store as needed)
  identity_adapter   — exposes slug_from_discord_user_id(user_id)
  store_adapter      — read_profile/write_profile/append_to_inbox/append_question
                       /append_todo/write_npc_knowledge/write_canonization
                       /update_style_preset
  recall_adapter     — exposes async recall(slug, query, *, obsidian)

The route handlers thread the same module-level singletons through; the
orchestrator does not import the concrete adapters so unit tests inject
mocks via the keyword args.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel

from app.vault_markdown import _parse_frontmatter

logger = logging.getLogger(__name__)

VALID_STYLE_PRESETS = frozenset(
    {"Tactician", "Lorekeeper", "Cheerleader", "Rules-Lawyer Lite"}
)


class PlayerInteractionRequest(BaseModel):
    """Verb-tagged orchestrator request.

    The Literal narrows to the verbs implemented in THIS slice. Plans 08/09/10
    widen the Literal as they add note/ask/npc/recall/todo/canonize. Pydantic
    rejects any unknown verb at the request boundary so every shipped commit
    stays green — no NotImplementedError, no stub raise.
    """

    verb: Literal["start", "style", "state", "note", "ask", "npc", "todo", "recall", "canonize"]
    user_id: str
    # Generic optional fields used across verbs.
    action: str | None = None
    preset: str | None = None
    style_preset: str | None = None
    character_name: str | None = None
    preferred_name: str | None = None
    text: str | None = None
    query: str | None = None
    npc_name: str | None = None
    note: str | None = None
    question_id: str | None = None
    outcome: str | None = None
    rule_text: str | None = None


class PlayerInteractionResult(BaseModel):
    slug: str
    verb: str
    requires_onboarding: bool = False
    data: dict | None = None
    message: str | None = None
    presets: list[str] | None = None


async def _check_onboarded(
    slug: str,
    *,
    store_adapter: Any,
) -> bool:
    """True iff profile.md exists AND its frontmatter has `onboarded: true`."""
    text = await store_adapter.read_profile(slug)
    if not text:
        return False
    fm = _parse_frontmatter(text)
    return bool(fm.get("onboarded") is True)


def _validate_style_preset(preset: str | None) -> str:
    """Closed-enum check — raise ValueError with the four valid presets listed."""
    if preset not in VALID_STYLE_PRESETS:
        raise ValueError(
            f"invalid style preset {preset!r}; valid presets: "
            f"Tactician, Lorekeeper, Cheerleader, Rules-Lawyer Lite"
        )
    return preset


async def handle_player_interaction(
    request: PlayerInteractionRequest,
    *,
    obsidian_client: Any,
    identity_adapter: Any,
    store_adapter: Any,
    recall_adapter: Any,
) -> PlayerInteractionResult:
    """Resolve slug, gate on onboarding, dispatch verb.

    Wave 2 slice covers start/style/state. Other verbs are gated and routed
    where their downstream adapter behaviour can be observed by the plan-02
    isolation/resolver tests (recall_adapter.recall and store_adapter.append_*),
    even though their full route-side behaviour ships in later plans.
    """
    slug = identity_adapter.slug_from_discord_user_id(request.user_id)

    # Verbs allowed pre-onboarding:
    #   - "start"        : creates the profile, must be allowed when not onboarded
    #   - "style:list"   : read-only preset enumeration
    is_style_list = request.verb == "style" and request.action == "list"
    pre_onboarding_allowed = request.verb == "start" or is_style_list

    onboarded = await _check_onboarded(slug, store_adapter=store_adapter)
    if not onboarded and not pre_onboarding_allowed:
        return PlayerInteractionResult(
            slug=slug,
            verb=request.verb,
            requires_onboarding=True,
            message=":pf player start to onboard before using this verb.",
        )

    # Validate style preset early so `style set` with an invalid preset raises
    # before any vault I/O. Validation runs even pre-onboarding only when the
    # gate has already approved the verb (style set is gated above).
    if request.verb == "style" and request.action == "set":
        _validate_style_preset(request.preset)

    match request.verb:
        case "start":
            profile: dict[str, Any] = {
                "slug": slug,
                "onboarded": True,
            }
            if request.character_name:
                profile["character_name"] = request.character_name
            if request.preferred_name:
                profile["preferred_name"] = request.preferred_name
            if request.style_preset:
                _validate_style_preset(request.style_preset)
                profile["style_preset"] = request.style_preset
            await store_adapter.write_profile(slug, profile)
            return PlayerInteractionResult(
                slug=slug, verb="start", data=profile
            )

        case "style":
            if request.action == "list":
                presets = sorted(VALID_STYLE_PRESETS)
                return PlayerInteractionResult(
                    slug=slug,
                    verb="style",
                    presets=presets,
                    data={"presets": presets},
                )
            # action == "set"
            await store_adapter.update_style_preset(slug, request.preset)
            return PlayerInteractionResult(
                slug=slug,
                verb="style",
                data={"style_preset": request.preset},
            )

        case "state":
            text = await store_adapter.read_profile(slug)
            fm = _parse_frontmatter(text or "") if text else {}
            return PlayerInteractionResult(
                slug=slug,
                verb="state",
                data={
                    "onboarded": bool(fm.get("onboarded")),
                    "style_preset": fm.get("style_preset"),
                    "character_name": fm.get("character_name"),
                    "preferred_name": fm.get("preferred_name"),
                },
            )

        case "note":
            # Plan 08 will widen behaviour; the seam routes the resolver-derived
            # slug to the inbox adapter so PVL-06/PVL-07 invariants hold today.
            await store_adapter.append_to_inbox(slug, request.text or "")
            return PlayerInteractionResult(slug=slug, verb="note")

        case "ask":
            await store_adapter.append_question(slug, request.text or "")
            return PlayerInteractionResult(slug=slug, verb="ask")

        case "npc":
            # Plan 37-08: derive npc_slug via the same slugify rule used by the
            # global Phase-29 NPC routes. Empty npc_name short-circuits with a
            # usage hint and no vault write — keeps the per-player NPC namespace
            # free of stray empty-slug files.
            from app.routes.npc import slugify  # noqa: PLC0415
            if not (request.npc_name or "").strip():
                return PlayerInteractionResult(
                    slug=slug,
                    verb="npc",
                    message="Usage: :pf player npc <npc_name> <note>",
                )
            npc_slug = slugify(request.npc_name or "")
            await store_adapter.write_npc_knowledge(
                slug, npc_slug, request.note or ""
            )
            return PlayerInteractionResult(slug=slug, verb="npc")

        case "todo":
            await store_adapter.append_todo(slug, request.text or "")
            return PlayerInteractionResult(slug=slug, verb="todo")

        case "recall":
            results = await recall_adapter.recall(
                slug, request.query or "", obsidian=obsidian_client
            )
            return PlayerInteractionResult(
                slug=slug, verb="recall", data={"results": results}
            )

        case "canonize":
            await store_adapter.write_canonization(
                slug,
                question_id=request.question_id,
                outcome=request.outcome,
                rule_text=request.rule_text,
            )
            return PlayerInteractionResult(slug=slug, verb="canonize")

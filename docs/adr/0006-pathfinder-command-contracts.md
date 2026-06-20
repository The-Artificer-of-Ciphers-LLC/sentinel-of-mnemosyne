# ADR-0006 — Pathfinder command contracts are noun-specific

**Status:** accepted
**Date:** 2026-06-20

Pathfinder command contracts are noun-specific Discord-side modules that map `:pf <noun>` command intent to Pathfinder module route names and payload shapes. They own outbound route strings and payload dictionaries only; response formatting and wildcard command parsing stay in the Discord adapters until those concerns earn separate deepening. This preserves locality at each noun's route seam without creating one broad shallow contract module.

The shared call value is `PathfinderModuleCall` in `interfaces/discord/pathfinder_types.py`. The first implementation slice moves the existing Player contract and a new Rule contract onto that value, updates the Rule adapter to use the Rule contract for route + payload construction, and validates generated payloads against the real Pathfinder route request models. Later slices should migrate Session, NPC, Harvest, Foundry, and Ingest contracts the same way.

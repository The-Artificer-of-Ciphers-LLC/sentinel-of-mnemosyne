# Sentinel persona is sourced from the Vault, not hardcoded

The Sentinel's system prompt — the **Sentinel persona** — lives at `sentinel/persona.md` in the
Vault and is read on every `POST /message` in parallel with the existing Hot tier reads. The
operator can edit the Sentinel's behaviour without a code change or a restart.

## Considered Options

- **Hardcoded class attribute on `MessageProcessor`.** Simplest. Rejected: the Sentinel persona is
  operator-tunable content, not a code constant. Bundling it with the processor put it in the
  wrong layer — every persona tweak required a code edit and a deploy.
- **Single-string config file (`message_prompt.py`).** A file with one string and no behaviour.
  Rejected: shallow module, didn't move the operator-tunable content out of the codebase.
- **Vault-sourced via the Sentinel namespace.** Chosen. Mirrors how the user's self lives in the
  Self namespace; the Sentinel's self lives in a parallel Sentinel namespace.

## Failure modes

The Vault is an operational dependency that already degrades gracefully when unreachable. The
Sentinel persona inherits the same posture, with one strict case:

- **Vault reachable, file missing (404)** at startup → hard fail. This is operator
  misconfiguration that should be surfaced loudly, not papered over.
- **Vault unreachable** at startup → continue with the hardcoded fallback persona. Preserves the
  validated graceful-degrade property: Sentinel Core starts even when Obsidian is down.
- **File disappears mid-run** (404 on a per-message read) → fall back to the hardcoded persona for
  that request and log a warning. Per-request user traffic is not 503'd over a vault edit.

The hardcoded fallback is the prior `SYSTEM_PROMPT` string, kept verbatim in `MessageProcessor`.

## Consequences

- One additional Obsidian read per message, parallelised inside the existing Hot tier
  `asyncio.gather`. No measurable latency cost.
- Sentinel Core's startup contract gains one strict case: if Obsidian is up but the persona file
  is missing, startup fails. Documented as an operator setup step.
- The `sentinel/` namespace is now reserved for operator-curated Sentinel self-definition. Future
  additions (e.g. `sentinel/capabilities.md`) follow the same pattern.

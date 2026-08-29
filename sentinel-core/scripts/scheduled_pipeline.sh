#!/bin/sh
# Scheduled 6 Rs pipeline run: Reduce -> Reflect -> Verify-gate -> Reweave -> Rethink.
#
# WHY THIS EXISTS
# The Reduce phase is what promotes captured entries out of the inbox queue and
# into notes/, which is the only namespace warm-tier recall actually searches
# (RecallConfig.exclude_prefixes excludes inbox/). Before this job the pipeline
# ran ONLY when someone triggered it by hand, so captured knowledge could sit
# undrained indefinitely and the Sentinel had nothing to recall.
#
# SCOPE (read before assuming this drains everything)
# _run_pipeline reads INBOX_PATH (inbox/_pending-classification.md) and
# parse_inbox()s its entries. It drains that QUEUE FILE. It does NOT pick up
# standalone inbox/*.md notes that NoteIntake filed directly because
# TOPIC_VAULT_PATH maps learning/reference to "inbox" -- those have no
# promotion path at all. That is a separate, known gap.
#
# AUTH
# The route's admin gate (_is_admin_route) checks SENTINEL_ADMIN_USER_IDS, which
# is already present in this container's environment, so no id is hardcoded
# here. The API key is read from the compose secret mount at request time and is
# never written into a config file or a log line.
#
# Invoked by ofelia job-exec inside the sentinel-core container.
# See security/pentest-agent/ofelia.ini.
set -eu

KEY_FILE=/run/secrets/sentinel_api_key
if [ ! -r "$KEY_FILE" ]; then
    echo "scheduled_pipeline: $KEY_FILE missing or unreadable" >&2
    exit 1
fi

# SENTINEL_ADMIN_USER_IDS is a comma-separated allowlist, or "*" for any id.
ADMIN=$(printf '%s' "${SENTINEL_ADMIN_USER_IDS:-}" | cut -d, -f1 | tr -d ' ')
if [ -z "$ADMIN" ]; then
    echo "scheduled_pipeline: SENTINEL_ADMIN_USER_IDS is unset; refusing to run" >&2
    exit 1
fi
if [ "$ADMIN" = "*" ]; then
    ADMIN=scheduler
fi

echo "scheduled_pipeline: starting 6 Rs pipeline run"
curl -fsS -m 60 -X POST http://localhost:8000/vault/pipeline/start \
    -H 'Content-Type: application/json' \
    -H "X-Sentinel-Key: $(cat "$KEY_FILE")" \
    -d "{\"user_id\":\"${ADMIN}\",\"mode\":\"pipeline\"}"
echo
echo "scheduled_pipeline: start acked (run is async; poll /vault/pipeline/status)"

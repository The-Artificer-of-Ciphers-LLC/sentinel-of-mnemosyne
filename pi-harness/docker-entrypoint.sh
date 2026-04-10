#!/bin/sh
# Create pi custom provider config from environment variables at container start.
# This runs before the main process so the models.json is ready when pi spawns.
set -e

mkdir -p /root/.pi/agent

cat > /root/.pi/agent/models.json << MODELS_EOF
{
  "providers": {
    "lmstudio": {
      "baseUrl": "${LMSTUDIO_BASE_URL}",
      "api": "openai-completions",
      "apiKey": "lm-studio",
      "compat": {
        "supportsDeveloperRole": false,
        "supportsReasoningEffort": false
      },
      "models": [
        { "id": "${PI_MODEL}" }
      ]
    }
  }
}
MODELS_EOF

echo "[entrypoint] pi models.json written for provider=lmstudio model=${PI_MODEL}"
exec "$@"

# DESIGN RULE: Services in this package must NOT import vendor AI SDKs directly.
# All AI inference must route through app.state.ai_provider (injected at startup).
# Violation of this rule will be caught by tests/test_ai_agnostic_guardrail.py.

"""Shared test fixtures for Sentinel Core tests."""
import os
import pytest

# Set env vars before any app import so pydantic-settings picks them up
os.environ.setdefault("SENTINEL_API_KEY", "test-key-for-pytest")


@pytest.fixture
def mock_lmstudio_response():
    """Mock response from LM Studio /v1/chat/completions."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello from mock LM Studio"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
    }


@pytest.fixture
def mock_lmstudio_models_response():
    """Mock response from LM Studio /api/v0/models/{model}."""
    return {"max_context_length": 8192, "id": "test-model"}

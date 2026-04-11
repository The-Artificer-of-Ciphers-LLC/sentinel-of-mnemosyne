"""pytest configuration for Discord interface tests."""


def pytest_configure(config):
    """Register asyncio_mode=auto for this test directory."""
    config.option.asyncio_mode = "auto"

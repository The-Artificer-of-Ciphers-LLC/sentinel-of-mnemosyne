"""pytest configuration for shared/ tests."""


def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: mark test as async")

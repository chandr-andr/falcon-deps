import falcon.asgi
import falcon.testing
import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def falcon_app() -> falcon.asgi.App:
    return falcon.asgi.App()

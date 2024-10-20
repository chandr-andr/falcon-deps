import pytest
import falcon.asgi
import falcon.testing


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def falcon_app() -> falcon.asgi.App:
    app = falcon.asgi.App()
    return app

import random
import uuid
from typing import Any

import falcon.asgi
import falcon.testing
import pytest
from pydantic import BaseModel


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def falcon_app() -> falcon.asgi.App:
    return falcon.asgi.App()


class TestRequestBodyPD(BaseModel):
    username: str
    user_id: int


@pytest.fixture
def test_request_data() -> dict[str, Any]:
    return {
        "username": uuid.uuid4().hex,
        "user_id": random.randint(1, 100),
    }

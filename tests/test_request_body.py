import typing
from typing import Any

import falcon.status_codes
import falcon.testing
import pytest
from falcon.asgi import Request, Response
from taskiq_dependencies import Depends

from falcon_deps.json_dep import Json
from falcon_deps.resource import InjectableResource
from tests.conftest import (
    TestRequestBodyPD,
)
from tests.utils import construct_client

pytestmark = pytest.mark.anyio


async def test_request_body_with_pd(
    falcon_app: falcon.asgi.App,
    test_request_data: dict[str, Any],
) -> None:
    class Resource(InjectableResource):
        async def on_post(
            self,
            request: Request,
            response: Response,
            request_data: TestRequestBodyPD = Depends(Json()),
        ) -> None:
            response.data = request_data.model_dump_json().encode()
            response.status = falcon.HTTP_703

    falcon_app.add_route(
        "/test",
        Resource(),
    )

    async with construct_client(falcon_app) as client:
        result: falcon.testing.Result = await client.simulate_post(
            "/test",
            json=test_request_data,
        )

    expected_status_code = 703
    assert result.status_code == expected_status_code

    request_data: TestRequestBodyPD = TestRequestBodyPD.model_validate_json(
        result.content,
    )
    assert request_data.user_id == test_request_data["user_id"]
    assert request_data.username == test_request_data["username"]


async def test_optional_request_body(
    falcon_app: falcon.asgi.App,
) -> None:
    class Resource(InjectableResource):
        async def on_post(
            self,
            request: Request,
            response: Response,
            request_data: typing.Optional[TestRequestBodyPD] = Depends(Json()),
        ) -> None:
            if request_data:
                response.data = request_data.model_dump_json().encode()
            response.status = falcon.HTTP_703

    falcon_app.add_route(
        "/test",
        Resource(),
    )

    async with construct_client(falcon_app) as client:
        result: falcon.testing.Result = await client.simulate_post(
            "/test",
        )

    expected_status_code = 703
    assert result.status_code == expected_status_code

    assert not result.content

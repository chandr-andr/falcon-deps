import falcon.asgi
import falcon.status_codes
import falcon.testing
import pytest
from taskiq_dependencies import Depends

from falcon_deps.resource import InjectableResource
from tests.utils import construct_client

pytestmark = pytest.mark.anyio


async def test_default_resource(
    falcon_app: falcon.asgi.App,
) -> None:
    class Resource:
        async def on_get(
            self,
            request: falcon.asgi.Request,
            response: falcon.asgi.Response,
        ) -> None:
            response.status = falcon.HTTP_703

    falcon_app.add_route(
        "/test",
        Resource(),
    )

    async with construct_client(falcon_app) as client:
        result: falcon.testing.Result = await client.simulate_get(
            "/test",
        )

    expected_status_code = 703
    assert result.status_code == expected_status_code


async def test_resource_with_func_dep(
    falcon_app: falcon.asgi.App,
) -> None:
    def dep_one(request: falcon.asgi.Request = Depends()) -> str:
        return str(request)

    class Resource(InjectableResource):
        async def on_get(
            self,
            request: falcon.asgi.Request,
            response: falcon.asgi.Response,
            dep_one: str = Depends(dep_one),
        ) -> None:
            response.text = dep_one

    falcon_app.add_route(
        "/test",
        Resource(),
    )

    async with construct_client(falcon_app) as client:
        result: falcon.testing.Result = await client.simulate_get(
            "/test",
        )

    assert "/test" in result.text


async def test_resource_with_class_dep(
    falcon_app: falcon.asgi.App,
) -> None:
    class DepOne:
        def __init__(
            self,
            request: falcon.asgi.Request = Depends(),
        ) -> None:
            self.request = request

    class Resource(InjectableResource):
        async def on_get(
            self,
            request: falcon.asgi.Request,
            response: falcon.asgi.Response,
            dep_one: DepOne = Depends(DepOne),
        ) -> None:
            response.text = str(dep_one.request)

    falcon_app.add_route(
        "/test",
        Resource(),
    )

    async with construct_client(falcon_app) as client:
        result: falcon.testing.Result = await client.simulate_get(
            "/test",
        )

    assert "/test" in result.text


async def test_resource_with_exclude_responder_from_inject(
    falcon_app: falcon.asgi.App,
) -> None:
    class DepOne:
        def __init__(
            self,
            request: falcon.asgi.Request = Depends(),
        ) -> None:
            self.request = request

    class Resource(InjectableResource):
        async def on_get(
            self,
            request: falcon.asgi.Request,
            response: falcon.asgi.Response,
            dep_one: DepOne = Depends(DepOne),
        ) -> None:
            response.text = str(dep_one.request)

    falcon_app.add_route(
        "/test",
        Resource(
            exclude_responder_from_inject={"on_get"},
        ),
    )

    async with construct_client(falcon_app) as client:
        result: falcon.testing.Result = await client.simulate_get(
            "/test",
        )

    expected_status_code = 500
    assert result.status_code == expected_status_code

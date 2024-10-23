import logging
from dataclasses import dataclass

from falcon.asgi import App, Request, Response
from taskiq_dependencies import Depends

from falcon_deps.request_body import RequestBody
from falcon_deps.resource import InjectableResource

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)


@dataclass
class TestData:
    test: str


def dep1(test_data: TestData = Depends(RequestBody())) -> TestData:
    return test_data


class TestRes(InjectableResource):
    async def on_post(
        self,
        request: Request,
        response: Response,
        dep1: TestData = Depends(dep1),
    ) -> None:
        print("result", dep1)


def get_app() -> App:
    app = App()
    app.add_route("/test", TestRes())
    return app

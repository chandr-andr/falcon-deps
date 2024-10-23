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


class TestRes(InjectableResource):
    async def on_post(
        self,
        request: Request,
        response: Response,
        test_data: TestData = Depends(RequestBody()),
    ) -> None:
        print("result", test_data)


def get_app() -> App:
    app = App()
    app.add_route("/test", TestRes())
    return app

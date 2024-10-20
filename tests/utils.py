import falcon.asgi
import falcon.testing


def construct_client(
    falcon_app: falcon.asgi.App,
) -> falcon.testing.TestClient:
    return falcon.testing.TestClient(falcon_app)

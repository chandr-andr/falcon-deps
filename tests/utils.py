import falcon.asgi
import falcon.testing


def construct_client(
    falcon_app: falcon.asgi.App,
):
    return falcon.testing.TestClient(falcon_app)

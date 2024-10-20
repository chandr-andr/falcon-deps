from typing import Any, Callable, Coroutine, Optional, Set, Union

from falcon.routing.util import SuffixedMethodNotFoundError
import falcon.asgi
from taskiq_dependencies import DependencyGraph, Depends
from falcon._typing import MethodDict
from falcon import constants


def _map_http_methods(
    resource: object,
    suffix: Optional[str] = None,
    exclude_responder_from_inject: Union[Set[str], None] = None,
) -> MethodDict:
    """Map resource methods name to methods of a resource object.

    The original of this function in in `falcon.routing.util.map_http_methods`.

    We changed original method a little bit, as we need
    to know the name of the class method, not HTTP method name.

    ### Parameters
    - `resource`: An object with *responder* methods, following the naming
        convention *on_\\**, that correspond to each method the resource
        supports. For example, if a resource supports GET and POST, it
        should define ``on_get(self, req, resp)`` and
        ``on_post(self, req, resp)``.

    - `suffix`: Optional responder name suffix for this route. If
        a suffix is provided, Falcon will map GET requests to
        ``on_get_{suffix}()``, POST requests to ``on_post_{suffix}()``,
        etc.
    - `exclude_responder_from_inject`: Methods names to exclude them
        from injecting. It means that these methods dont use `Depends()`.

    Returns:
        dict: A mapping of HTTP methods to explicitly defined resource responders.

    """
    responder_name_map = {}

    if exclude_responder_from_inject:
        exclude_methods = exclude_responder_from_inject
    else:
        exclude_methods = set()

    exclude_methods.add("on_websocket")

    for method in constants.COMBINED_METHODS:
        try:
            responder_name = "on_" + method.lower()
            if suffix:
                responder_name += "_" + suffix

            if responder_name in exclude_methods:
                continue
            responder = getattr(resource, responder_name)
        except AttributeError:
            # resource does not implement this method
            pass
        else:
            # Usually expect a method, but any callable will do
            if callable(responder):
                responder_name_map[responder_name] = responder

    # If suffix is specified and doesn't map to any methods, raise an error
    if suffix and not responder_name_map:
        raise SuffixedMethodNotFoundError(
            "No responders found for the specified suffix",
        )

    return responder_name_map


class InjectableResource:
    """
    Dependency injector for resources.

    Usage:
    ```
    class MyResource(InjectableResource):
        ...

    app.add_route(
        "/test",
        MyResource(
            suffix="test", # Not necessary
        ),
        suffix="test", # Not necessary
    )
    ```
    """

    def __init__(
        self,
        suffix: Optional[str] = None,
        exclude_responder_from_inject: Union[Set[str], None] = None,
    ) -> None:
        """Create new Resource handler with dependency injection.

        Create dependency graph for each responder in a resource,
        replace responders with wrapped responders with
        dependency injector support.

        ### Parameters:
        - `suffix`: suffix for resource responders.
        - `exclude_responder_from_inject`: if case you have responders
        that don't need dependency injection, you can exclude them.
        """
        self.responder_name_map = _map_http_methods(
            self,
            suffix=suffix,
            exclude_responder_from_inject=exclude_responder_from_inject,
        )

        self.graph_map = {
            method: DependencyGraph(self.responder_name_map[method])
            for method in self.responder_name_map
        }
        for responder_name in self.responder_name_map:
            modified_method = self.handle_with_graph_http(
                responder_name=responder_name,
            )
            setattr(self, responder_name, modified_method)

    def handle_with_graph_http(
        self,
        responder_name: str,
    ) -> Callable[
        [
            falcon.asgi.Request,
            falcon.asgi.Response,
            Any,
        ],
        Coroutine[Any, Any, None],
    ]:
        """Wrapper for real responders in this resource.

        ### Returns:
        Return new responders with dependency injection.
        """
        original_method = self.responder_name_map[responder_name]
        graph = self.graph_map[responder_name]

        async def _handle_with_graph(
            request: falcon.asgi.Request,
            response: falcon.asgi.Response,
            **params: Any,
        ) -> None:
            async with graph.async_ctx(
                {
                    falcon.asgi.Request: request,
                },
            ) as ctx:
                dep_kwargs = await ctx.resolve_kwargs()
                await original_method(  # type: ignore[misc]
                    request,
                    response,  # type: ignore[arg-type]
                    **dep_kwargs,
                    **params,
                )

        return _handle_with_graph  # type: ignore


async def dep1(request: falcon.asgi.Request = Depends()) -> int:
    print(request.auth)
    return 123


class TestResource(InjectableResource):
    async def on_get(
        self,
        request: falcon.asgi.Request,
        response: falcon.asgi.Response,
        dep1: int = Depends(dep1),
    ) -> None:
        print(dep1)


def create_app():
    app = falcon.asgi.App()
    app.add_route("/test", TestResource())
    return app

import copy
from typing import Any, Optional

from falcon.routing.util import map_http_methods
from taskiq_dependencies import DependencyGraph


class InjectableResource:
    """
    Dependency injector for resources.

    Usage:
    ```
    app.add_route(
        "/test",
        InjectableResource(
            MyView,
            suffix="test", # Not necessary
        ),
        suffix="test", # Not necessary
    )
    ```
    """

    def __init__(
        self,
        original_route: object,
        suffix: Optional[str] = None,
    ) -> None:
        methods_map = map_http_methods(
            original_route,
            suffix=suffix,
        )

        self.original_handler = copy.copy(original_route)

        self.graph_map = {
            method: DependencyGraph(methods_map[method])
            for method in methods_map
        }

    def __getattr__(self, name: str) -> Any:
        attr_from_original_handler = getattr(self.original_handler, name)
        if attr_from_original_handler:
            return attr_from_original_handler

        raise AttributeError

import inspect
import json
from typing import Any, Optional, Tuple, Type, Union

import pydantic
from falcon import HTTPBadRequest
from falcon.asgi import Request
from taskiq_dependencies import Depends, ParamInfo

OPTIONAL_ = "Optional"


class Json:
    """
    Get and validate body from request.

    You can pass any class that can be constructed:
    pydantic model, dataclass, class and etc.

    This dependency grabs request body and validates
    it against given schema.

    You should provide schema with type hints.
    """

    def __init__(
        self,
        handle_exceptions: Optional[Tuple[Type[Exception]]] = None,
    ) -> None:
        """
        Initialize RequestBody.

        ### Parameters:
        - `handle_exceptions`: what exceptions must be handled when
            try to convert request body into class.
        """
        self.handle_exceptions = handle_exceptions or (Exception,)
        self.type_initialized = False
        self.type_cache: "Union[pydantic.TypeAdapter[Any], None]" = None

    async def __call__(
        self,
        request: Request = Depends(),
        param_info: ParamInfo = Depends(),
    ) -> Any:
        """Create new class from given type hint."""
        if not self.type_initialized:
            if (
                param_info.definition
                and param_info.definition.annotation != inspect.Parameter.empty
            ):
                self.type_cache = pydantic.TypeAdapter(param_info.definition.annotation)
            else:
                self.type_cache = None

            self.type_initialized = True

        request_body_bytes = await request.stream.read()

        if not request_body_bytes:
            request_body = None
        else:
            try:
                request_body = json.loads(request_body_bytes.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                description = (
                    "Could not decode the request body. The "
                    "JSON was incorrect or not encoded as "
                    "UTF-8."
                )
                raise HTTPBadRequest(  # noqa: B904
                    title="Malformed JSON",
                    description=description,
                )

        if self.type_cache is None:
            return request_body

        try:
            return self.type_cache.validate_python(request_body)
        except self.handle_exceptions:
            description = "Could not construct class from request body."
            raise HTTPBadRequest(  # noqa: B904
                title="Incorrect JSON",
                description=description,
            )

import inspect
import json
from typing import Any, Type

import falcon
from falcon.asgi import Request
from taskiq_dependencies import Depends, ParamInfo


class RequestBody:
    """
    Get and validate body from request.

    This dependency grabs request body and validates
    it against given schema.

    You should provide schema with typehints.
    """

    def __init__(self) -> None:
        self.type_initialized = False
        self.type_cache: Type[object] | None = None

    async def __call__(
        self,
        request: Request = Depends(),
        param_info: ParamInfo = Depends(),
    ) -> Any:
        request_body_bytes = await request.stream.read()

        try:
            request_body = json.loads(request_body_bytes.decode("utf-8"))
            print(request_body)
        except (ValueError, UnicodeDecodeError):
            description = (
                "Could not decode the request body. The "
                "JSON was incorrect or not encoded as "
                "UTF-8."
            )

            raise falcon.HTTPBadRequest(title="Malformed JSON", description=description)

        if not self.type_initialized:
            if (
                param_info.definition
                and param_info.definition.annotation != inspect.Parameter.empty
            ):
                self.type_cache = param_info.definition.annotation
            else:
                self.type_cache = None

        if self.type_cache is None:
            return request_body

        return self.type_cache(**request_body)

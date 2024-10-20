# Falcon-deps
Dependency injector for [Falcon Framework](https://github.com/falconry/falcon) based on [taskiq-dependencies](https://github.com/taskiq-python/taskiq-dependencies).

## Installation

Install with pip
```bash
pip install falcon-deps
```

Install with poetry
```bash
poetry add falcon-deps
```

## Usage

### Start Usage
It's simple as possible.

```python
from falcon_deps import InjectableResource
from falcon.asgi import App, Request, Response
from taskiq_dependencies import Depends


# Imagine we have a database pool.
async def db_pool(
    # Retrieve request object from the actual request.
    request: Request = Depends(),
) -> ConnectionPool:
    return request.context._pool


class Resource(InjectableResource):
    async def on_get(
        self,
        request: Request,
        response: Response,
        # Retrieve database pool as a dependency
        db_pool: ConnctionPool = Depends(db_pool)
    ) -> None:
        ...


app = App()
app.add_route(
    "/test",
    Resource(),
)
```

### Advanced Usage
Falcon gives option to specify suffix for resource.
If you want to use suffix with `InjectableResource` you need to pass suffix to `InjectableResource` too.

```python
app.add_route(
    "/test",
    Resource(suffix="bob",),
    suffix="bob",
)
```

If some of methods in Resource don't need dependency injection, it's possible to remove them from injection with `exclude_responder_from_inject`.

```python
app.add_route(
    "/test",
    Resource(
        exclude_responder_from_inject={
            # Remove on_get and on_post methods from injection.
            "on_get",
            "on_post",
        },
    ),
)
```

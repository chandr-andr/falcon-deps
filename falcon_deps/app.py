import asyncio
from typing import Any, Dict, Optional
import falcon
import falcon.asgi
import falcon.routing.compiled
from falcon import HTTPBadRequest
from falcon.asgi._asgi_helpers import _wrap_asgi_coroutine_func
from falcon.asgi._asgi_helpers import _validate_asgi_scope
from falcon._typing import AsgiReceive
from falcon._typing import AsgiSend
from falcon._typing import AsgiResponderCallable
from falcon._typing import _UNSET
from falcon.asgi.app import _BODILESS_STATUS_CODES, _TYPELESS_STATUS_CODES, _EVT_RESP_EOF
from falcon.asgi.structures import SSEvent
from inspect import isasyncgenfunction
from falcon.asgi_spec import EventType
from falcon.constants import MEDIA_JSON


class DIApp(falcon.asgi.App):
    @_wrap_asgi_coroutine_func
    async def __call__(  # type: ignore[override] # noqa: C901
        self,
        scope: Dict[str, Any],
        receive: AsgiReceive,
        send: AsgiSend,
    ) -> None:
        # NOTE(kgriffs): The ASGI spec requires the 'type' key to be present.
        scope_type: str = scope['type']

        # PERF(kgriffs): This should usually be present, so use a
        #   try..except
        try:
            asgi_info: Dict[str, str] = scope['asgi']
        except KeyError:
            # NOTE(kgriffs): According to the ASGI spec, "2.0" is
            #   the default version.
            asgi_info = scope['asgi'] = {'version': '2.0'}

        try:
            spec_version: Optional[str] = asgi_info['spec_version']
        except KeyError:
            spec_version = None

        try:
            http_version: str = scope['http_version']
        except KeyError:
            http_version = '1.1'

        spec_version = _validate_asgi_scope(scope_type, spec_version, http_version)

        if scope_type != 'http':
            # PERF(vytas): Evaluate the potentially recurring WebSocket path
            #   first (in contrast to one-shot lifespan events).
            if scope_type == 'websocket':
                await self._handle_websocket(spec_version, scope, receive, send)
                return

            # NOTE(vytas): Else 'lifespan' -- other scope_type values have been
            #   eliminated by _validate_asgi_scope at this point.
            await self._call_lifespan_handlers(spec_version, scope, receive, send)
            return

        # NOTE(kgriffs): Per the ASGI spec, we should not proceed with request
        #   processing until after we receive an initial 'http.request' event.
        first_event = await receive()
        first_event_type = first_event['type']
        # PERF(vytas): Inline the value of EventType.HTTP_DISCONNECT in this
        #   critical code path.
        if first_event_type == 'http.disconnect':
            # NOTE(kgriffs): Bail out immediately to minimize resource usage
            return

        # NOTE(kgriffs): This is the only other type defined by the ASGI spec,
        #   but we just assert it to make it easier to track down a potential
        #   incompatibility with a future spec version.
        # PERF(vytas): Inline the value of EventType.HTTP_REQUEST in this
        #   critical code path.
        assert first_event_type == 'http.request'

        req = self._request_type(
            scope, receive, first_event=first_event, options=self.req_options
        )
        resp = self._response_type(options=self.resp_options)

        resource: Optional[object] = None
        params: Dict[str, Any] = {}

        dependent_mw_resp_stack: list = []
        mw_req_stack, mw_rsrc_stack, mw_resp_stack = self._middleware

        req_succeeded = False

        try:
            if req.method in self._META_METHODS:
                raise HTTPBadRequest()

            # NOTE(ealogar): The execution of request middleware
            # should be before routing. This will allow request mw
            # to modify the path.
            # NOTE: if flag set to use independent middleware, execute
            # request middleware independently. Otherwise, only queue
            # response middleware after request middleware succeeds.
            if self._independent_middleware:
                for process_request in mw_req_stack:
                    await process_request(req, resp)  # type: ignore[operator]

                    if resp.complete:
                        break
            else:
                for process_request, process_response in mw_req_stack:  # type: ignore[misc, assignment]
                    if process_request and not resp.complete:
                        await process_request(req, resp)  # type: ignore[operator]

                    if process_response:
                        dependent_mw_resp_stack.insert(0, process_response)

            if not resp.complete:
                # NOTE(warsaw): Moved this to inside the try except
                # because it is possible when using object-based
                # traversal for _get_responder() to fail.  An example is
                # a case where an object does not have the requested
                # next-hop child resource. In that case, the object
                # being asked to dispatch to its child will raise an
                # HTTP exception signaling the problem, e.g. a 404.
                responder: AsgiResponderCallable
                responder, params, resource, req.uri_template = self._get_responder(req)  # type: ignore[assignment]

        except Exception as ex:
            if not await self._handle_exception(req, resp, ex, params):
                raise

        else:
            try:
                # NOTE(kgriffs): If the request did not match any
                # route, a default responder is returned and the
                # resource is None. In that case, we skip the
                # resource middleware methods. Resource will also be
                # None when a middleware method already set
                # resp.complete to True.
                if resource:
                    # Call process_resource middleware methods.
                    for process_resource in mw_rsrc_stack:
                        await process_resource(req, resp, resource, params)

                        if resp.complete:
                            break

                if not resp.complete:
                    route = self._router_search(req.path, req=req)
                    if not route:
                        await responder(req, resp, **params)
                    else:
                        resource, _, params, _ = route
                        if hasattr(
                            resource,
                            "graph_map",
                        ) and resource.graph_map.get(req.method):
                            graph = resource.graph_map[req.method]
                            async with graph.async_ctx(
                                {
                                    falcon.asgi.Request: req,
                                },
                            ) as ctx:
                                kwargs = await ctx.resolve_kwargs()
                                await responder(req, resp, **kwargs, **params)
                        else:
                            await responder(req, resp, **params)

                req_succeeded = True

            except Exception as ex:
                if not await self._handle_exception(req, resp, ex, params):
                    raise

        # Call process_response middleware methods.
        for process_response in mw_resp_stack or dependent_mw_resp_stack:
            try:
                await process_response(req, resp, resource, req_succeeded)

            except Exception as ex:
                if not await self._handle_exception(req, resp, ex, params):
                    raise

                req_succeeded = False

        data: Optional[bytes] = b''

        try:
            # NOTE(vytas): It is only safe to inline Response.render_body()
            #   where we can be sure it hasn't been overridden, either directly
            #   or by modifying the behavior of its dependencies.
            if self._standard_response_type:
                # PERF(vytas): inline Response.render_body() in this critical code
                #   path in order to shave off an await.
                text = resp.text
                if text is None:
                    data = resp._data

                    if data is None and resp._media is not None:
                        # NOTE(kgriffs): We use a special _UNSET singleton since
                        #   None is ambiguous (the media handler might return None).
                        if resp._media_rendered is _UNSET:
                            opt = resp.options
                            if not resp.content_type:
                                resp.content_type = opt.default_media_type

                            handler, serialize_sync, _ = opt.media_handlers._resolve(
                                resp.content_type, opt.default_media_type
                            )

                            if serialize_sync:
                                resp._media_rendered = serialize_sync(resp._media)
                            else:
                                resp._media_rendered = await handler.serialize_async(
                                    resp._media, resp.content_type
                                )

                        data = resp._media_rendered
                else:
                    try:
                        # NOTE(kgriffs): Normally we expect text to be a string
                        data = text.encode()
                    except AttributeError:
                        # NOTE(kgriffs): Assume it was a bytes object already
                        data = text  # type: ignore[assignment]

            else:
                # NOTE(vytas): Custom response type.
                data = await resp.render_body()

        except Exception as ex:
            if not await self._handle_exception(req, resp, ex, params):
                raise

            req_succeeded = False

        resp_status: int = resp.status_code
        default_media_type: Optional[str] = self.resp_options.default_media_type

        if req.method == 'HEAD' or resp_status in _BODILESS_STATUS_CODES:
            #
            # PERF(vytas): move check for the less common and much faster path
            # of resp_status being in {204, 304} here; NB: this builds on the
            # assumption _TYPELESS_STATUS_CODES <= _BODILESS_STATUS_CODES.
            #
            # NOTE(kgriffs): Based on wsgiref.validate's interpretation of
            # RFC 2616, as commented in that module's source code. The
            # presence of the Content-Length header is not similarly
            # enforced.
            #
            # NOTE(kgriffs): Assuming the same for ASGI until proven otherwise.
            #
            if resp_status in _TYPELESS_STATUS_CODES:
                default_media_type = None
            elif (
                # NOTE(kgriffs): If they are going to stream using an
                #   async generator, we can't know in advance what the
                #   content length will be.
                (data is not None or not resp.stream)
                and req.method == 'HEAD'
                and resp_status not in _BODILESS_STATUS_CODES
                and 'content-length' not in resp._headers
            ):
                # NOTE(kgriffs): We really should be returning a Content-Length
                #   in this case according to my reading of the RFCs. By
                #   optionally using len(data) we let a resource simulate HEAD
                #   by turning around and calling it's own on_get().
                resp._headers['content-length'] = str(len(data)) if data else '0'

            await send(
                {
                    # PERF(vytas): Inline the value of
                    #   EventType.HTTP_RESPONSE_START in this critical code path.
                    'type': 'http.response.start',
                    'status': resp_status,
                    'headers': resp._asgi_headers(default_media_type),
                }
            )

            await send(_EVT_RESP_EOF)

            # PERF(vytas): Check resp._registered_callbacks directly to shave
            #   off a function call since this is a hot/critical code path.
            if resp._registered_callbacks:
                self._schedule_callbacks(resp)
            return

        # PERF(vytas): Operate directly on the resp private interface to reduce
        #   overhead since this is a hot/critical code path.
        if resp._sse:
            sse_emitter = resp._sse
            if isasyncgenfunction(sse_emitter):
                raise TypeError(
                    'Response.sse must be an async iterable. This can be obtained by '
                    'simply executing the async generator function and then setting '
                    'the result to Response.sse, e.g.: '
                    'resp.sse = some_asyncgen_function()'
                )

            # NOTE(kgriffs): This must be done in a separate task because
            #   receive() can block for some time (until the connection is
            #   actually closed).
            async def watch_disconnect() -> None:
                while True:
                    received_event = await receive()
                    if received_event['type'] == EventType.HTTP_DISCONNECT:
                        break

            watcher = asyncio.create_task(watch_disconnect())

            await send(
                {
                    'type': EventType.HTTP_RESPONSE_START,
                    'status': resp_status,
                    'headers': resp._asgi_headers('text/event-stream'),
                }
            )

            # PERF(vytas): Check resp._registered_callbacks directly to shave
            #   off a function call since this is a hot/critical code path.
            if resp._registered_callbacks:
                self._schedule_callbacks(resp)

            sse_handler, _, _ = self.resp_options.media_handlers._resolve(
                MEDIA_JSON, MEDIA_JSON, raise_not_found=False
            )

            # TODO(kgriffs): Do we need to do anything special to handle when
            #   a connection is closed?
            async for event in sse_emitter:
                if not event:
                    event = SSEvent()

                # NOTE(kgriffs): According to the ASGI spec, once the client
                #   disconnects, send() acts as a no-op. We have to check
                #   the connection state using watch_disconnect() above.
                await send(
                    {
                        'type': EventType.HTTP_RESPONSE_BODY,
                        'body': event.serialize(sse_handler),
                        'more_body': True,
                    }
                )

                if watcher.done():  # pragma: no py39,py310 cover
                    break

            watcher.cancel()
            try:
                await watcher
            except asyncio.CancelledError:
                pass

            await send({'type': EventType.HTTP_RESPONSE_BODY})
            return

        if data is not None:
            # PERF(kgriffs): Böse mußt sein. Operate directly on resp._headers
            #   to reduce overhead since this is a hot/critical code path.
            # NOTE(kgriffs): We always set content-length to match the
            #   body bytes length, even if content-length is already set. The
            #   reason being that web servers and LBs behave unpredictably
            #   when the header doesn't match the body (sometimes choosing to
            #   drop the HTTP connection prematurely, for example).
            resp._headers['content-length'] = str(len(data))

            await send(
                {
                    # PERF(vytas): Inline the value of
                    #   EventType.HTTP_RESPONSE_START in this critical code path.
                    'type': 'http.response.start',
                    'status': resp_status,
                    'headers': resp._asgi_headers(default_media_type),
                }
            )

            await send(
                {
                    # PERF(vytas): Inline the value of
                    #   EventType.HTTP_RESPONSE_BODY in this critical code path.
                    'type': 'http.response.body',
                    'body': data,
                }
            )

            # PERF(vytas): Check resp._registered_callbacks directly to shave
            #   off a function call since this is a hot/critical code path.
            if resp._registered_callbacks:
                self._schedule_callbacks(resp)
            return

        stream = resp.stream
        if not stream:
            resp._headers['content-length'] = '0'

        await send(
            {
                # PERF(vytas): Inline the value of
                #   EventType.HTTP_RESPONSE_START in this critical code path.
                'type': 'http.response.start',
                'status': resp_status,
                'headers': resp._asgi_headers(default_media_type),
            }
        )

        if stream:
            # Detect whether this is one of the following:
            #
            #   (a) async file-like object (e.g., aiofiles)
            #   (b) async generator
            #   (c) async iterator
            #

            if hasattr(stream, 'read'):
                try:
                    while True:
                        data = await stream.read(self._STREAM_BLOCK_SIZE)
                        if data == b'':
                            break
                        else:
                            await send(
                                {
                                    'type': EventType.HTTP_RESPONSE_BODY,
                                    # NOTE(kgriffs): Handle the case in which
                                    #   data is None
                                    'body': data or b'',
                                    'more_body': True,
                                }
                            )
                finally:
                    if hasattr(stream, 'close'):
                        await stream.close()
            else:
                # NOTE(kgriffs): Works for both async generators and iterators
                try:
                    async for data in stream:
                        # NOTE(kgriffs): We can not rely on StopIteration
                        #   because of Pep 479 that is implemented starting
                        #   with Python 3.7. AFAICT this is only an issue
                        #   when using an async iterator instead of an async
                        #   generator.
                        if data is None:
                            break

                        await send(
                            {
                                'type': EventType.HTTP_RESPONSE_BODY,
                                'body': data,
                                'more_body': True,
                            }
                        )
                except TypeError as ex:
                    if isasyncgenfunction(stream):
                        raise TypeError(
                            'The object assigned to Response.stream appears to '
                            'be an async generator function. A generator '
                            'object is expected instead. This can be obtained '
                            'simply by calling the generator function, e.g.: '
                            'resp.stream = some_asyncgen_function()'
                        )

                    raise TypeError(
                        'Response.stream must be a generator or implement an '
                        '__aiter__ method. Error raised while iterating over '
                        'Response.stream: ' + str(ex)
                    )
                finally:
                    # NOTE(vytas): This could be DRYed with the above identical
                    #   twoliner in a one large block, but OTOH we would be
                    #   unable to reuse the current try.. except.
                    if hasattr(stream, 'close'):
                        await stream.close()

        await send(_EVT_RESP_EOF)

        # PERF(vytas): Check resp._registered_callbacks directly to shave
        #   off a function call since this is a hot/critical code path.
        if resp._registered_callbacks:
            self._schedule_callbacks(resp)

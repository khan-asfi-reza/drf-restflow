# APIView and AsyncAPIView

`APIView` and `AsyncAPIView` are the two non-generic base classes in the
restflow views module. Both inherit from DRF's APIView. The sync class
adds the helper surface; the async class also swaps the dispatch loop
for an async one.

## APIView

`restflow.views.APIView` is a sync APIView that adds the restflow helper
methods on top of DRF's APIView. The dispatch loop is unchanged. Use it
where async is not desired but the helpers still are -- for example,
when integrating with sync-only middleware or porting an existing DRF
codebase incrementally.

```python
from restflow.views import APIView
from rest_framework.pagination import PageNumberPagination

class UserView(APIView):
    serializer_class = UserSer
    pagination_class = PageNumberPagination

    def get(self, request):
        return self.paginated_response(User.objects.all())

    def post(self, request):
        ser = self.validated_serializer()
        user = ser.save()
        return self.serialized_response(user, status=201)
```

Helpers available on APIView.

- get_context
- get_serializer_class, get_request_serializer_class,
  get_response_serializer_class
- get_pagination_class
- get_serializer
- validated_serializer
- serialized_response
- paginated_response

Each helper resolves through the corresponding getter. Override the
getter rather than the attribute when the choice depends on the request
or on the action being performed.

## AsyncAPIView

`restflow.views.AsyncAPIView` switches dispatch to `async def` and
provides async variants for the helpers. The handler methods (get, post,
put, patch, delete) become coroutines.

```python
from restflow.views import AsyncAPIView

class UserView(AsyncAPIView):
    serializer_class = UserSer
    pagination_class = PageNumberPagination

    async def get(self, request):
        qs = User.objects.all()
        return await self.apaginated_response(qs)

    async def post(self, request):
        ser = await self.avalidated_serializer()
        user = await ser.asave()
        return await self.aserialized_response(user, status=201)
```

The class declares `view_is_async = True`, which lets Django's URL
resolver and DRF's introspection treat it as an async view.

The sync helpers remain available: AsyncAPIView inherits the sync
helper surface as well, so a partially async view can still call
`self.serialized_response(...)` if it has nothing to await.

## Async hook fall-back

An async view can be paired with sync DRF authentication, permission,
throttle, pagination, and filter backend classes without any changes
to those components. Native async implementations are picked up
automatically when present.

## Exception handling

`ahandle_exception` mirrors DRF's `handle_exception` step by step.

- `NotAuthenticated` and `AuthenticationFailed` exceptions are decorated
  with `auth_header` from `get_authenticate_header`. If no authenticate
  header is available, the status is forced to 403 instead of 401.
- The exception handler returned by `get_exception_handler()` is
  invoked. The result is awaited if it is a coroutine.
- A None response means the handler chose not to handle the exception;
  `raise_uncaught_exception` re-raises it.
- Otherwise the response is marked with `exception = True` and returned.

To customise error handling, set the standard DRF
`EXCEPTION_HANDLER` setting, or override `ahandle_exception` and call
`super().ahandle_exception(exc)` from inside.

## Object permissions

`acheck_object_permissions(request, obj)` is the async variant of DRF's
`check_object_permissions`. Generic views call it from `aget_object`
once the object has been resolved. Custom handlers that fetch an
object directly should call it explicitly.

```python
async def custom(self, request, pk):
    obj = await self.get_queryset().aget(pk=pk)
    await self.acheck_object_permissions(request, obj)
    return await self.aserialized_response(obj)
```

## Helper methods

Every helper exists in two flavours. Sync helpers live on `APIView`
and the inherited surface of `AsyncAPIView`. Async helpers (prefixed
with `a`) live on `AsyncAPIView`.

### get_context

Returns the dict passed as `context` to every serializer built through
`get_serializer`. Defaults to `{"request": self.request, "view": self}`.

Override to inject extra context.

```python
def get_context(self):
    ctx = super().get_context()
    ctx["organization"] = self.request.organization
    return ctx
```

### get_serializer_class / get_request_serializer_class / get_response_serializer_class

The three getters that drive serializer resolution. The helpers call
them with `direction="request"` or `direction="response"` and pick
the right one.

| Direction      | Getter                          | Falls back to        |
| -------------- | ------------------------------- | -------------------- |
| (default)      | get_serializer_class            | -                    |
| request input  | get_request_serializer_class    | get_serializer_class |
| response data  | get_response_serializer_class   | get_serializer_class |

### get_pagination_class

Returns the pagination class used by `paginated_response` and
`apaginated_response`. Defaults to `self.pagination_class`. The viewset
overrides this method to honour ActionConfig overrides.

### get_serializer

Builds a serializer instance with the request context. Accepts
`serializer_class=` to override the resolved class explicitly.

### validated_serializer / avalidated_serializer

Builds a serializer for the request input direction, runs `is_valid` (or
awaits `ais_valid`), and returns the serializer. Errors raise
`ValidationError` and bubble up to the exception handler.

```python
ser = await self.avalidated_serializer()
user = await ser.asave()
```

Pass `data=` to validate something other than `request.data`.

### serialized_response / aserialized_response

Builds a serializer for the response direction, serializes the
instance, and wraps the data in a Response.

```python
return self.serialized_response(user, status=201)
```

Pass `many=True` for a sequence. Pass `post_fetches=[...]` to run
PostFetch joins before serialisation. The async variant awaits each
PostFetch via `afetch` when available.

### paginated_response / apaginated_response

Paginates a queryset, serializes the resulting page (or the entire
queryset if pagination is disabled), and returns a Response.

```python
return await self.apaginated_response(queryset, post_fetches=[latest_review])
```

If `pagination_class` is None at the class level and not overridden by
keyword, the helper serialises the full queryset without paginating.

## PostFetch helpers

The two private helpers `perform_post_fetches` and `aperform_post_fetches`
back the `post_fetches=` keyword on the response helpers. They iterate
the supplied PostFetch instances and call `fetch` (or `afetch`) on each.
Custom view code rarely calls them directly -- pass `post_fetches=` to
the response helper instead.

For a single object, the helpers wrap it in a single-element list before
running the fetches and unwrap it afterwards.

## Custom dispatch hooks

Every step on the async dispatch path is overridable.

| Hook                     | Override to                                   |
| ------------------------ | --------------------------------------------- |
| dispatch                 | Replace the loop entirely                     |
| ainitial                 | Add cross-cutting setup before authentication |
| aperform_authentication  | Inject custom auth flow                       |
| acheck_permissions       | Add cross-cutting permission logic            |
| acheck_throttles         | Pre or post-process throttle results          |
| ahandle_exception        | Customise error mapping                       |
| afinalize_response       | Add common headers, log responses             |

A common pattern is to log the resolved user inside `afinalize_response`
without touching the rest of the loop.

```python
async def afinalize_response(self, request, response, *args, **kwargs):
    response = await super().afinalize_response(request, response, *args, **kwargs)
    response["X-User"] = str(request.user)
    return response
```

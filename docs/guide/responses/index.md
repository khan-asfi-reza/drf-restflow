# Streaming responses

Restflow ships three async streaming responses for endpoints
that produce large or open-ended payloads. Each one wraps an async
iterable and writes results to the client as they are produced,
without buffering the full payload in memory.

## Responses

All three classes subclass `django.http.StreamingHttpResponse` and
take an async iterable as the first argument. Django drives the
iterable through the ASGI server, writing each yielded chunk to the
client as soon as it is produced.

```python
from restflow.responses import (
    NDJSONResponse,
    SSEResponse,
    StreamingJSONListResponse,
)
```

The JSON variants encode each item with `DjangoJSONEncoder` by
default, which handles datetime, date, time, UUID, Decimal, and
Django Promise instances.

## Response Types


- **StreamingJSONListResponse**: emits a single JSON array
  element-by-element. Best for export endpoints and large list
  endpoints where the consumer expects a JSON array but the result
  set is too large to buffer.
- **NDJSONResponse**: emits one JSON object per line. Best for log
  streams, incremental update consumers, and command-line tools that
  understand jsonlines.
- **SSEResponse**: emits Server-Sent Events. Best for real-time push
  use cases such as notifications, progress updates, and live
  counters. Browser clients consume SSE through the EventSource API.

If the response fits comfortably in memory, return a regular DRF
`Response` instead. Streaming responses trade memory for latency,
and they bypass DRF's renderer and content negotiation pipeline.

## Async iterable contract

All three responses accept any async iterable. The most common
shapes are an async generator and an async iteration over a queryset.

```python
async def gen():
    yield {"id": 1}
    yield {"id": 2}
```

```python
async def gen():
    async for product in Product.objects.all():
        yield {"id": product.id, "name": product.name}
```

The iterable is awaited once per item. JSON variants require items
to be JSON-serialisable through the active encoder.

For very large querysets, iterate with chunks so the database
connection releases work in batches rather than holding a single
long transaction.

```python
async def gen():
    qs = Product.objects.all().iterator(chunk_size=500)
    async for product in qs:
        yield {"id": product.id, "name": product.name}
```

## StreamingJSONListResponse

Emits a single JSON array, one element at a time, with no whitespace
between elements.

```python
from restflow.responses import StreamingJSONListResponse


async def stream_products():
    async for product in Product.objects.all().iterator():
        yield {"id": product.id, "name": product.name, "price": product.price}


async def list_products(request):
    return StreamingJSONListResponse(stream_products())
```

Output shape:

```json
[{"id":1,"name":"A","price":10},{"id":2,"name":"B","price":20}]
```

An empty iterable produces `[]`. The opening `[` is yielded
immediately so the client receives the start of the array even
before the first item is computed. The closing `]` is emitted in a
finally block, so the array always terminates correctly even if the
iterable raises.

The default content type is `application/json`. Override it through
the standard `content_type=` keyword if a custom subtype is needed.

```python
return StreamingJSONListResponse(
    stream_products(),
    content_type="application/vnd.api+json",
)
```

## NDJSONResponse

Emits newline-delimited JSON: one object per line, with a trailing
newline after the last entry.

```python
from restflow.responses import NDJSONResponse


async def stream_events():
    async for event in audit_log_iterator():
        yield {"ts": event.ts, "actor": event.actor, "action": event.action}


async def export_events(request):
    return NDJSONResponse(stream_events())
```

Output shape:

```
{"ts":"2026-01-01T00:00:00Z","actor":"a","action":"login"}
{"ts":"2026-01-01T00:00:01Z","actor":"b","action":"logout"}
```

The default content type is `application/x-ndjson`. NDJSON pairs
well with `jq` and any tool that consumes jsonlines.

```bash
curl -N http://localhost:8000/api/events/ | jq '.actor'
```

The same encoder customisation as `StreamingJSONListResponse`
applies. Pass `encoder=` to swap in a custom encoder.

## SSEResponse

Emits Server-Sent Events. Items in the iterable can be plain strings
or dicts.

```python
import asyncio
from restflow.responses import SSEResponse


async def heartbeat():
    while True:
        yield "tick"
        await asyncio.sleep(1)


async def heartbeat_view(request):
    return SSEResponse(heartbeat())
```

A string item becomes a single-frame event with the text in the
`data` field:

```
data: tick

```

Dict items support the SSE field set:

| Key | Description |
| --- | --- |
| `data` | The payload. Strings pass through untouched. Non-strings are JSON-encoded with `DjangoJSONEncoder`. Multi-line strings are split into multiple `data:` lines per the SSE spec. |
| `event` | The event type. The browser dispatches a custom event of this name. |
| `id` | The event id. Browsers send this back in the `Last-Event-ID` header on reconnect. |
| `retry` | Reconnect delay in milliseconds. The browser uses this when the connection drops. |

```python
async def progress():
    yield {"event": "start", "data": "job-42"}
    for pct in range(0, 101, 10):
        yield {"event": "progress", "id": str(pct), "data": {"pct": pct}}
    yield {"event": "done", "data": "job-42"}
```

Frame structure for a structured event:

```
id: 50
event: progress
data: {"pct": 50}

```

The handler rejects CR or LF in the `id`, `event`, and `retry`
fields with a `ValueError`, since those characters would split or
corrupt the frame. Strip newlines from these values before yielding.

### Headers set by SSEResponse

Two headers are set automatically:

- `Cache-Control: no-cache` -- prevents intermediate caches from
  collapsing repeated polls.
- `X-Accel-Buffering: no` -- disables nginx response buffering on
  the SSE path. Without this, nginx waits to fill its buffer before
  flushing, which delays event delivery.

The default content type is `text/event-stream`.

### Reconnection

Browsers using `EventSource` automatically reconnect when the
connection drops. They send the most recent `id` value back as the
`Last-Event-ID` request header. The application is responsible for
honouring this header by skipping forward in the iterable; the
response itself does not track or replay history.

```python
async def event_stream(request, since_id):
    async for ev in events_after(since_id):
        yield {"id": str(ev.id), "data": ev.payload}


async def events_view(request):
    since_id = request.headers.get("Last-Event-ID", "0")
    return SSEResponse(event_stream(request, since_id))
```

## Headers and status

All three responses forward keyword arguments to
`StreamingHttpResponse`. Set the status, headers, or content type
through standard kwargs.

```python
return NDJSONResponse(
    stream_events(),
    status=200,
    headers={"X-Total-Count": "1234"},
)
```

For CORS, set the relevant Access-Control headers on the response.
Browser SSE clients require both the `EventSource` constructor and
the response to agree on credentials.

```python
response = SSEResponse(events())
response["Access-Control-Allow-Origin"] = "https://app.example.com"
response["Access-Control-Allow-Credentials"] = "true"
return response
```

## Encoder customisation

The JSON variants accept an `encoder=` keyword. The default is
`DjangoJSONEncoder`, which already handles datetime, date, time,
UUID, Decimal, and Django Promise objects.

For custom types, subclass `DjangoJSONEncoder` and pass the class
through `encoder=`.

```python
import json
from decimal import Decimal
from django.core.serializers.json import DjangoJSONEncoder
from restflow.responses import StreamingJSONListResponse


class FloatDecimalEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


async def stream_orders():
    async for order in Order.objects.all().iterator():
        yield {"id": order.id, "total": order.total}


async def orders_view(request):
    return StreamingJSONListResponse(
        stream_orders(),
        encoder=FloatDecimalEncoder,
    )
```

The encoder is instantiated once per response. Avoid stateful
encoders that depend on per-call cleanup, since the same instance
encodes every item.

For SSE, dict events with non-string `data` are encoded with
`DjangoJSONEncoder` directly. To customise SSE payload encoding,
serialise the value upstream and pass it as a string.

```python
import json
from decimal import Decimal


def _encode(value):
    return json.dumps(value, cls=FloatDecimalEncoder)


async def events():
    yield {"event": "order", "data": _encode({"total": Decimal("9.99")})}
```

## Error handling during streaming

Once a streaming response has started, the HTTP status and headers
are already on the wire. An exception raised mid-stream truncates
the response; the client sees a partial body and the connection
closes.

For NDJSON and SSE, the framing tolerates partial output: each line
or frame is self-contained. Wrap the iterable to catch errors and
emit a final error frame so the consumer can detect the failure.

```python
async def safe_events():
    try:
        async for ev in real_events():
            yield ev
    except Exception as exc:
        yield {"event": "error", "data": str(exc)}
```

For `StreamingJSONListResponse`, the closing bracket is always
emitted (the iteration is wrapped in try/finally), so the JSON array
remains parseable. The underlying error is not communicated through
the response body. Log it server-side and rely on out-of-band
monitoring, or switch to NDJSON if a final error record is needed.

## Backpressure and ASGI

Each yielded chunk passes through the ASGI server's send queue.
Slow consumers cause the queue to fill, and the iterable stalls
until the client drains the buffer.

For huge result sets, iterate with `chunk_size` so the database
connection releases work in batches. Combining a streaming response
with `Model.objects.iterator(chunk_size=N)` keeps memory bounded
even when the result set runs into millions of rows.

```python
async def stream_all():
    async for row in Order.objects.all().iterator(chunk_size=1000):
        yield {"id": row.id, "total": row.total}
```

Reverse proxies can buffer responses by default. For SSE, the
`X-Accel-Buffering: no` header instructs nginx to flush. For NDJSON
and the JSON list response under nginx, set the same header
explicitly when streaming behind a proxy.

```python
response = NDJSONResponse(stream_all())
response["X-Accel-Buffering"] = "no"
return response
```

## Integration with views

Streaming responses work with both function views and class-based
async views.

```python
from django.views.decorators.http import require_GET


@require_GET
async def export_view(request):
    return NDJSONResponse(stream_events())
```

In a DRF async view, return the streaming response from the action.
Authentication and permission checks still run inside `ainitial`
before the response is constructed, so unauthenticated callers
never reach the iterable.

```python
from rest_framework.views import APIView


class EventStream(APIView):
    permission_classes = [IsAuthenticated]

    async def get(self, request):
        return SSEResponse(stream_events_for(request.user))
```

DRF's renderer pipeline does not run on these responses. They
subclass `StreamingHttpResponse`, not `Response`.

## Next steps

- [API reference](../../api/responses/index.md): full signatures for
  the three response classes.

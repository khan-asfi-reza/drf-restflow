import json

from django.core.serializers.json import DjangoJSONEncoder
from django.http import StreamingHttpResponse


class StreamingJSONListResponse(StreamingHttpResponse):
    """
    Streams a JSON array one element at a time from an async iterable.
    Useful for endpoints that return a long list without buffering the whole response in memory.
    """

    def __init__(self, async_iterable, *, encoder=None, **kwargs):
        self._iter = async_iterable
        self._encoder_cls = encoder or DjangoJSONEncoder
        kwargs.setdefault("content_type", "application/json")
        super().__init__(self.stream(), **kwargs)

    async def stream(self):
        encoder = self._encoder_cls()
        yield "["
        first = True
        try:
            async for item in self._iter:
                if not first:
                    yield ","
                yield encoder.encode(item)
                first = False
        finally:
            yield "]"


class NDJSONResponse(StreamingHttpResponse):
    """
    Streams newline-delimited JSON, one object per line, from an async iterable.
    Useful for log-style endpoints and clients that consume incremental updates.
    """

    def __init__(self, async_iterable, *, encoder=None, **kwargs):
        self._iter = async_iterable
        self._encoder_cls = encoder or DjangoJSONEncoder
        kwargs.setdefault("content_type", "application/x-ndjson")
        super().__init__(self.stream(), **kwargs)

    async def stream(self):
        encoder = self._encoder_cls()
        async for item in self._iter:
            yield encoder.encode(item) + "\n"


class SSEResponse(StreamingHttpResponse):
    """
    Streams Server-Sent Events from an async iterable.
    Items may be strings or dicts.
    """

    def __init__(self, async_iterable, **kwargs):
        self._iter = async_iterable
        kwargs.setdefault("content_type", "text/event-stream")
        super().__init__(self.stream(), **kwargs)
        self["Cache-Control"] = "no-cache"
        self["X-Accel-Buffering"] = "no"

    async def stream(self):
        async for ev in self._iter:
            yield format_sse(ev)


def reject_control_chars(name: str, value) -> str:
    rendered = value if isinstance(value, str) else str(value)
    if "\r" in rendered or "\n" in rendered:
        msg = (
            f"SSE event field {name!r} must not contain CR or LF characters. "
            "Strip newlines before passing the value."
        )
        raise ValueError(msg)
    return rendered


def format_sse(event) -> str:
    """Formats server sent events. Items may be strings or dicts with data, event, id, and retry keys."""
    if isinstance(event, str):
        return format_sse({"data": event})
    lines = []
    if "id" in event:
        lines.append(f"id: {reject_control_chars('id', event['id'])}")
    if "event" in event:
        lines.append(f"event: {reject_control_chars('event', event['event'])}")
    if "retry" in event:
        lines.append(f"retry: {reject_control_chars('retry', event['retry'])}")
    if "data" in event:
        payload = event["data"]
        if not isinstance(payload, str):
            payload = json.dumps(payload, cls=DjangoJSONEncoder)
        for line in payload.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"

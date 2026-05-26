import asyncio

from rest_framework.response import Response as DRFResponse


class Response(DRFResponse):
    """
    DRF Response with an async render entry point.

    render() is inherited from Django's SimpleTemplateResponse and runs every
    registered callback synchronously, matching the existing contract.
    arender() does the same work on the live event loop and awaits any
    callback that is a coroutine function.

    Async views await arender(); Django's sync handler keeps calling
    render() unchanged.
    """

    async def arender(self):
        """Render content and await any coroutine-function post-render callbacks."""
        if self._is_rendered:
            return self
        self.content = self.rendered_content
        self._is_rendered = True
        retval = self
        for callback in self._post_render_callbacks:
            if asyncio.iscoroutinefunction(callback):
                new = await callback(retval)
            else:
                new = callback(retval)
            if new is not None:
                retval = new
        return retval

# Dispatchers

The dispatcher layer routes invalidation work to the right runtime.
See the [Dispatchers guide](../../guide/caching/dispatchers.md) for
an overview and per-broker setup.

::: restflow.caching.Dispatcher
    options:
      members:
        - dispatch
        - validate_config
        - batch_key
        - settings

::: restflow.caching.InlineDispatcher

::: restflow.caching.ThreadPoolDispatcher

::: restflow.caching.AsyncIODispatcher

::: restflow.caching.CeleryDispatcher

::: restflow.caching.DjangoRqDispatcher

::: restflow.caching.DjangoQDispatcher

::: restflow.caching.DramatiqDispatcher

::: restflow.caching.register_dispatcher

::: restflow.caching.registered_dispatcher_names

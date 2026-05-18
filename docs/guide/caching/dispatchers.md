# Dispatchers

A dispatcher decides where an `InvalidationRule`'s work runs:
synchronously on the request thread, on a thread pool, on an asyncio
event loop, or handed off to a task broker.

Pass a dispatcher name on the rule:

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    dispatcher="celery",
    dispatcher_config={"queue": "cache-invalidation"},
)
```

`dispatcher` accepts either a registered name (string) or a
`Dispatcher` subclass.

## Comparison

| Name | Process | Durability | Setup | Best for |
| --- | --- | --- | --- | --- |
| `inline` | Request thread, on commit | None | None | Default. Fast invalidation, no extra services. |
| `threadpool` | Process-wide thread pool | None | None | Slower invalidation that should not block the request. Loses work on process exit. |
| `asyncio` | Asyncio event loop | None | None | Async views and async signal handlers. |
| `celery` | Celery worker | Broker durability | Celery + broker | Project already runs celery, or invalidation needs retries and dead-lettering. |
| `django_rq` | django-rq worker | Redis durability | django-rq + redis | Redis-backed queue without celery. |
| `django_q` | django-q worker | DB or redis durability | django-q (or django-q2) | Django-native queue with built-in scheduling. |
| `dramatiq` | Dramatiq worker | Broker durability | Dramatiq + broker | Project already runs dramatiq, or its actor middleware is preferred. |

## inline

The default. Runs invalidation work synchronously on the same thread
as the model save, inside the save's `transaction.on_commit`
callback. No broker, no worker process, no extra dependencies.

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
)
```

Move off `inline` once invalidation gets expensive enough to slow the
request that triggered the save.

## threadpool

Runs invalidation off the request thread on a process-wide
`ThreadPoolExecutor`.

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    dispatcher="threadpool",
)
```

Configuration:

| Key | Default | Effect |
| --- | --- | --- |
| `MAX_WORKERS` | `4` | Pool size. Settings-level only. |

```python
RESTFLOW_SETTINGS = {
    "CACHE_SETTINGS": {
        "DISPATCHER_SETTINGS": {
            "threadpool": {"MAX_WORKERS": 8},
        },
    },
}
```

The pool is built lazily on the first dispatch. Its size is fixed
once created; later rules that ask for a different size share the
existing pool.

## asyncio

Schedules invalidation on the running asyncio event loop. The
dispatcher creates an `asyncio.Task` against the running loop with
`arun_cache_rules`, so the rules run concurrently with the request
handler that triggered them. Tasks are tracked on
`AsyncIODispatcher._pending_tasks` and removed via
`task.add_done_callback`, so the loop holds a strong reference for
the duration of execution.

When the calling thread has no running event loop (Django can run
`transaction.on_commit` callbacks on a sync thread), the dispatcher
falls back to the synchronous worker entry `run_cache_rules` and
runs invalidation inline. The fallback is logged at `DEBUG` so the
mode is visible in development.

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    dispatcher="asyncio",
)
```

`supports_batching` is `False`, so each rule fires its own task.
The dispatcher does not need any infrastructure beyond the running
ASGI loop.

### Configuration

| Setting | Default | Effect |
|---|---|---|
| `RESTFLOW_SETTINGS["CACHE_SETTINGS"]["DISPATCHER_SETTINGS"]["asyncio"]["RAISE_EXCEPTION"]` | `None` | When `True`, the worker re-raises framework-level errors. Falls back to the global `DISPATCHER_RAISE_EXCEPTION` when `None`. |

### When to pick it

Pick `asyncio` for ASGI deployments that already have a running
loop and want invalidation to run without a worker process. The
fallback to `inline` keeps sync code paths working without extra
configuration.

## celery

Hand invalidation off to a celery task. The bundled task is
`restflow.caching.tasks.task_run_cache_rules`, registered as a
`@shared_task` so `app.autodiscover_tasks(["restflow"])` picks it up.

### Install

```bash
pip install drf-restflow[celery]
```

### Wire it up

```python
# myproject/celery.py
from celery import Celery

app = Celery("myproject")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

### Use the dispatcher

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    dispatcher="celery",
    dispatcher_config={
        "task_name": "myapp.tasks.bust",
        "queue": "cache-invalidation",
    },
)
```

### Configuration

| Key | Default | Effect |
| --- | --- | --- |
| `task_name` | `"restflow.caching.tasks.task_run_cache_rules"` | Celery task to call. |
| `queue` | `None` | Queue name. `None` lets celery pick its default. |
| `RAISE_EXCEPTION` | `None` | Override the global `DISPATCHER_RAISE_EXCEPTION` setting for celery rules. |

The dispatcher prefers `apply_async` when the task is registered on
the local app and falls back to `send_task` for tasks defined only on
a remote worker. The `apply_async` path respects
`task_always_eager`, which is what tests use.

## django-rq

Hand invalidation off to django-rq.

### Install

```bash
pip install drf-restflow[django-rq]
```

### Wire it up

```python
# settings.py
RQ_QUEUES = {
    "default": {
        "HOST": "localhost",
        "PORT": 6379,
        "DB": 0,
    },
    "cache-invalidation": {
        "HOST": "localhost",
        "PORT": 6379,
        "DB": 0,
    },
}
```

Run a worker:

```bash
python manage.py rqworker cache-invalidation
```

### Use the dispatcher

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    dispatcher="django_rq",
    dispatcher_config={"queue": "cache-invalidation"},
)
```

### Configuration

| Key | Default | Effect |
| --- | --- | --- |
| `queue` | `"default"` | RQ queue name. |
| `function_path` | `"restflow.caching.tasks.run_cache_rules"` | Dotted path to the worker callable. |
| `RAISE_EXCEPTION` | `None` | Override the global setting. |

## django-q

Hand invalidation off to django-q (or django-q2).

### Install

```bash
pip install drf-restflow[django-q]
```

### Wire it up

```python
# settings.py
Q_CLUSTER = {
    "name": "myproject",
    "workers": 4,
    "timeout": 60,
    "retry": 120,
    "queue_limit": 50,
    "bulk": 10,
    "orm": "default",
}
```

Run a cluster:

```bash
python manage.py qcluster
```

### Use the dispatcher

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    dispatcher="django_q",
    dispatcher_config={"group": "cache-invalidation"},
)
```

### Configuration

| Key | Default | Effect |
| --- | --- | --- |
| `cluster` | `None` | Cluster name (`Q_CLUSTER["name"]`). |
| `group` | `None` | Optional task group label that shows up in the django-q admin. |
| `function_path` | `"restflow.caching.tasks.run_cache_rules"` | Dotted path to the worker callable. |
| `RAISE_EXCEPTION` | `None` | Override the global setting. |

## dramatiq

Hand invalidation off to a dramatiq actor.

### Install

```bash
pip install drf-restflow[dramatiq]
```

### Register the actor on workers

The producer side registers the actor lazily on the first dispatch.
On the worker side, import the dispatcher module from the project's
tasks module so the actor is registered before the worker starts
consuming, or call `register_actor()` explicitly:

```python
# myapp/tasks.py
from restflow.caching.dispatchers.dramatiq import register_actor

register_actor()
```

### Use the dispatcher

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    dispatcher="dramatiq",
    dispatcher_config={"queue": "cache-invalidation"},
)
```

### Configuration

| Key | Default | Effect |
| --- | --- | --- |
| `queue` | `"default"` | Dramatiq queue name. |
| `actor_name` | `"restflow.task_run_cache_rules"` | Dramatiq actor name. |
| `RAISE_EXCEPTION` | `None` | Override the global setting. |

## Registering a custom dispatcher

To run invalidation on a runtime not listed above, subclass
`Dispatcher`, give it a stable `name`, and register it. After
registration, rules can pick it up by name.

```python
import abc
from restflow.caching import Dispatcher, register_dispatcher


@register_dispatcher
class MyDispatcher(Dispatcher):
    name = "my-runtime"

    def dispatch(self, *, rule_ids, rule_kwargs, **context):
        # Hand the work off to the runtime here. Implementations
        # must log and swallow their own errors so a failing
        # dispatcher does not crash the model save that triggered it.
        ...
```

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    dispatcher="my-runtime",
)
```

`registered_dispatcher_names()` returns the sorted list of all
registered names.

## Error handling across dispatchers

Errors that escape the registry are caught and logged by default. To
make errors propagate (so a broker retries or dead-letters), set
`raise_exception=True`. The resolution order, highest priority
first:

1. `InvalidationRule.raise_exception`.
2. The per-dispatcher `RAISE_EXCEPTION` settings entry.
3. `RESTFLOW_SETTINGS["CACHE_SETTINGS"]["DISPATCHER_RAISE_EXCEPTION"]`
   (default `False`).

When a batch mixes explicit values, `True` wins so the error
surfaces.

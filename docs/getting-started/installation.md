# Installation

Restflow is a declarative library on top of Django REST Framework.
It covers caching, filtering, type-driven serializers, async
authentication, async permissions, a full async view and viewset
stack, async pagination, async throttling, streaming responses, a
unified exception handler, OpenAPI schema generation, and an async
test client and case suite. This page covers the install, the
required Django setup, and the optional extras for each feature.

## Requirements

- Python 3.11 or higher
- Django 3.2 or higher
- Django REST Framework 3.14 or higher

## Install the package

```bash
pip install drf-restflow
```

With uv
```bash
uv add drf-restflow
```

## Django apps

Restflow ships two Django apps. Add the ones that match the
features used in the project.

`restflow.caching` registers post-save and post-delete signal
handlers on Django startup. Required for any project that uses
`@cache_result` with `invalidates_on=[...]`.

`restflow.authentication` ships the `BlacklistedToken` model used by
`ModelBlacklistBackend`. Required only when revoking JWTs through the
model-backed blacklist (`CacheBlacklistBackend` does not need this
app).

```python
# settings.py
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "restflow.caching",
    "restflow.authentication",
]
```

After adding `restflow.authentication`, run migrations to create the
blacklist table:

```bash
python manage.py migrate
```

With uv
```bash
uv run python manage.py migrate
```

## Cache backend

The caching layer plugs into Django's cache framework and works with
any configured backend.

A small set of features only works on a redis-compatible backend:

- `CachedWrapper.delete_by_prefix(...)` and the async
  `adelete_by_prefix(...)`.
- `CachedWrapper.invalidate_all()` and the async `ainvalidate_all()`.
- Any `InvalidationRule` that needs to wipe a partition rather than a
  single cache key (rules without an exact key match, or rules that
  use `rewarm=True` over a partition).

These calls rely on `delete_pattern`, which Django's local-memory and
database cache backends do not implement. Without a redis-compatible
backend they raise; the rest of the caching API still works on any
backend. 

```bash
pip install drf-restflow[redis]
```

```bash
uv add 'drf-restflow[redis]'
```

```python
# settings.py
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    },
}
```

## Task brokers for invalidation dispatch

Each `InvalidationRule` decides where the work runs through its
`dispatcher`. The default is `inline`, which runs the invalidation on
the request thread inside `transaction.on_commit`. When invalidation
becomes expensive, or when it should keep running across deploys,
switching to a broker-backed dispatcher is appropriate.

The dispatcher names below match the value passed to
`InvalidationRule(dispatcher=...)`.

### celery

Celery suits projects that already use celery, projects where
invalidation work fans out to many partitions, and projects that want
retries and dead-letter handling on cache work.

```bash
pip install drf-restflow[celery]
```

```bash
uv add 'drf-restflow[celery]'
```

The bundled task is `restflow.caching.tasks.task_run_cache_rules`. It
is registered as a `@shared_task` and is picked up by
`app.autodiscover_tasks(["restflow"])` automatically. When a project
calls `autodiscover_tasks()` without arguments, also list `"restflow"`
explicitly.

```python
# myproject/celery.py
from celery import Celery

app = Celery("myproject")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    dispatcher="celery",
    dispatcher_config={"queue": "cache-invalidation"},
)
```

To point invalidation at a different task name, set
`RESTFLOW_SETTINGS["CACHE_SETTINGS"]["DISPATCHER_SETTINGS"]["celery"]["TASK_NAME"]`,
or pass `task_name=` in `dispatcher_config`.

### django-rq

django-rq suits projects that already run django-rq workers and
prefer a redis-backed queue.

```bash
pip install drf-restflow[django-rq]
```

```bash
uv add 'drf-restflow[django-rq]'
```

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

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    dispatcher="django_rq",
    dispatcher_config={"queue": "cache-invalidation"},
)
```

Workers run with the standard django-rq command:

```bash
python manage.py rqworker cache-invalidation
```

The bundled worker callable is `restflow.caching.tasks.run_cache_rules`.
Override with `function_path=` in `dispatcher_config` to point at a
different callable.

### django-q (django-q2)

django-q suits projects that want a Django-native task queue that
runs without an extra broker process and supports task scheduling out
of the box.

```bash
pip install drf-restflow[django-q]
```

```bash
uv add 'drf-restflow[django-q]'
```

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

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    dispatcher="django_q",
    dispatcher_config={"group": "cache-invalidation"},
)
```

Run a worker cluster:

```bash
python manage.py qcluster
```

The bundled worker callable is `restflow.caching.tasks.run_cache_rules`.

### dramatiq

dramatiq suits projects that already run dramatiq, and projects that
want its actor model and built-in middleware (rate limiting, retries,
results) for cache invalidation.

```bash
pip install drf-restflow[dramatiq]
```

```bash
uv add 'drf-restflow[dramatiq]'
```

The bundled actor is registered lazily on the producer side. On the
worker side, import the dispatcher module from a tasks module so the
actor is registered before the worker starts consuming, or call
`register_actor()` explicitly:

```python
# myapp/tasks.py
from restflow.caching.dispatchers.dramatiq import register_actor

register_actor()
```

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    dispatcher="dramatiq",
    dispatcher_config={"queue": "cache-invalidation"},
)
```

The default actor name is `"restflow.task_run_cache_rules"`. Override
with `actor_name=` in `dispatcher_config`, or through
`RESTFLOW_SETTINGS["CACHE_SETTINGS"]["DISPATCHER_SETTINGS"]["dramatiq"]["ACTOR_NAME"]`.

### threadpool

Runs invalidation off the request thread on a process-wide
`ThreadPoolExecutor`. Work that has not
finished is lost if the process exits. Useful when invalidation is
too slow to run inline.

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    dispatcher="threadpool",
)
```

Pool size defaults to four workers and is configurable through
`RESTFLOW_SETTINGS["CACHE_SETTINGS"]["DISPATCHER_SETTINGS"]["threadpool"]["MAX_WORKERS"]`.

### asyncio

Schedules invalidation on the running asyncio event. Intended for async views and async signal
handlers. Falls back to inline execution when no event loop is
running.

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    dispatcher="asyncio",
)
```

### inline (default)

Runs invalidation synchronously on the request thread inside
`transaction.on_commit`. No setup required. This is the default when
no `dispatcher` is set on the rule.

## Authentication extras

The built-in `JWTAuthentication` requires no extra dependencies. 
The optional `simplejwt` extra adds an adapter
for projects using `djangorestframework-simplejwt`.

```bash
pip install drf-restflow[simplejwt]
```

```bash
uv add 'drf-restflow[simplejwt]'
```

The adapter exposes
`restflow.authentication.simplejwt.SimpleJWTAuthentication`, which
inherits simplejwt's validation logic and adds an async user lookup
so it can plug into the async view stack.

## OpenAPI schema (drf-spectacular)

To generate OpenAPI schemas through `drf-spectacular`, install the
`spectacular` extra and point DRF at `RestflowAutoSchema`:

```bash
pip install drf-restflow[spectacular]
```

```bash
uv add 'drf-restflow[spectacular]'
```

```python
# settings.py
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "restflow.spectacular.RestflowAutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Example API",
    "VERSION": "1.0.0",
}
```


## PostgreSQL

The PostgreSQL filtering features (full-text search, array fields,
trigram similarity, range fields) need a PostgreSQL driver.

```bash
# psycopg2
pip install drf-restflow[postgres]
uv add 'drf-restflow[postgres]'

# psycopg3
pip install drf-restflow[postgres-psycopg3]
uv add 'drf-restflow[postgres-psycopg3]'
```

## All optional extras at a glance

| Extra | Use case | pip | uv |
| --- | --- | --- | --- |
| `redis` | Cache backend that supports prefix-based invalidation | `pip install drf-restflow[redis]` | `uv add 'drf-restflow[redis]'` |
| `celery` | Run cache invalidation as celery tasks | `pip install drf-restflow[celery]` | `uv add 'drf-restflow[celery]'` |
| `django-rq` | Run cache invalidation through django-rq | `pip install drf-restflow[django-rq]` | `uv add 'drf-restflow[django-rq]'` |
| `django-q` | Run cache invalidation through django-q2 | `pip install drf-restflow[django-q]` | `uv add 'drf-restflow[django-q]'` |
| `dramatiq` | Run cache invalidation through dramatiq | `pip install drf-restflow[dramatiq]` | `uv add 'drf-restflow[dramatiq]'` |
| `postgres` | psycopg2 driver for PostgreSQL filtering features | `pip install drf-restflow[postgres]` | `uv add 'drf-restflow[postgres]'` |
| `postgres-psycopg3` | psycopg3 driver for PostgreSQL filtering features | `pip install drf-restflow[postgres-psycopg3]` | `uv add 'drf-restflow[postgres-psycopg3]'` |
| `simplejwt` | Adapter for djangorestframework-simplejwt | `pip install drf-restflow[simplejwt]` | `uv add 'drf-restflow[simplejwt]'` |
| `spectacular` | OpenAPI schema generation through drf-spectacular | `pip install drf-restflow[spectacular]` | `uv add 'drf-restflow[spectacular]'` |

## Compatibility

| Python | Django | DRF |
| --- | --- | --- |
| 3.11+ | 3.2+ | 3.14+ |

## Next steps

- [Quick Start](quickstart.md): short walkthroughs for each feature.
- [Basic Concepts](concepts.md): the mental model behind every
  subsystem.
- Guides: [Caching](../guide/caching/index.md),
  [Filtering](../guide/filtering/filterset.md),
  [Serializers](../guide/serializers/index.md),
  [Authentication](../guide/authentication/index.md),
  [Permissions](../guide/permissions/index.md),
  [Views](../guide/views/index.md),
  [Pagination](../guide/pagination/index.md),
  [Throttling](../guide/throttling/index.md),
  [Responses](../guide/responses/index.md),
  [Exception handler](../guide/exception-handler/index.md),
  [Spectacular](../guide/spectacular/index.md),
  [Testing](../guide/testing/index.md).

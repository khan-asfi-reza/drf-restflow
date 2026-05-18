# Invalidation Rules

`InvalidationRule` connects a Django model's `post_save` and
`post_delete` signals to a cached function. When the rule fires, the
wrapper either drops or refreshes the relevant cache entries.

Rules are passed to `@cache_result(invalidates_on=[...])`. Each rule
points at one model.

## Field mapping

The most common shape is one model field mapping to one wrapper
keyword argument.

```python
from restflow.caching import cache_result, InvalidationRule


@cache_result(
    key_constructor=UserPayloadKey,
    ttl=300,
    invalidates_on=[
        InvalidationRule(
            model=User,
            field_mapping={"user_id": "id"},
        ),
    ],
)
def get_user_payload(user_id: int): ...
```

`field_mapping={"user_id": "id"}` reads as: when a `User` is saved or
deleted, take its `id` attribute and call the wrapper's
`delete_by_prefix(user_id=<id>)`.

The wrapper falls back to `delete_cache(...)` when the targeted
argument is not part of the partition. Partition-only fields use
`delete_by_prefix`, and non-partition fields use the exact-key form.

### require_args

`require_args` controls whether the rule should run when fields in
`field_mapping` resolve to `None` on the saving instance. Three
forms:

| Value | Behaviour |
| --- | --- |
| `True` (default) | Every mapped field must be non-null. If any resolves to `None`, the rule is skipped silently. Safe choice that prevents accidentally invalidating the `None` partition. |
| `False` | `None` values pass through into the wrapper's kwargs, so the rule can target the `team_id=None` partition or similar. The rule runs regardless. |
| `list[str]` | Only the named fields are required. Any other field may resolve to `None` and pass through. The rule is skipped silently if any listed field is `None`. |

```python
InvalidationRule(
    model=Membership,
    field_mapping={"user_id": "user_id", "team_id": "team_id"},
    require_args=["user_id"],
)
```

This rule runs whenever `user_id` is set, even if `team_id` is
`None`.

## Custom invalidator

For transforms, derived values, multiple invalidations per save, or
custom routing, set `invalidator` to a callable (or a dotted-path
string).

```python
def invalidate_user_caches(wrapper, instance, **_):
    wrapper.delete_by_prefix(user_id=instance.id)
    if instance.team_id:
        wrapper.delete_by_prefix(team_id=instance.team_id)


InvalidationRule(
    model=User,
    invalidator=invalidate_user_caches,
)
```

The invalidator receives `(wrapper, instance, **extras)`. The
`extras` dict may include `signal_type`, `instance_created`, and
`update_fields` depending on what the function declares (or whether
it accepts `**kwargs`).

`field_mapping` and `invalidator` are mutually exclusive on a single
rule. Setting both raises `ValueError` at construction time.

A dotted-path string is resolved lazily on the first call:

```python
InvalidationRule(
    model=User,
    invalidator="myapp.invalidators.invalidate_user_caches",
)
```

## Pre-save gates

Three attributes filter when a rule runs based on the save itself.
They apply to both the field-mapping path and the custom-invalidator
path.

### trigger_on_create

By default, rules do not run on the `post_save` signal that follows
`Model.objects.create()`. The reasoning is that there is nothing to
invalidate yet for a freshly created row. Set `trigger_on_create=True`
when the cache spans the whole table, for example a "list all
users" cache.

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    trigger_on_create=True,
)
```

### watch_fields

When set, `post_save` only fires the rule if the save's
`update_fields` includes one of the listed field names. The default
value `None` means every save fires the rule.

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    watch_fields=["email", "username"],
)
```

`update_fields` is the argument passed to `Model.save(update_fields=)`.
Saves without `update_fields` go through every rule regardless.

### invalidate_when

A mapping from attribute name to expected value. The rule fires only
when every entry matches the saving instance. Prefix a key with `!`
to negate the comparison.

```python
InvalidationRule(
    model=Article,
    field_mapping={"article_id": "id"},
    invalidate_when={"status": "published", "!archived": True},
)
```

## Refresh instead of delete

Set `rewarm=True` to recompute and re-cache the value instead of
dropping it. Useful for hot keys where the next request would just
recompute anyway.

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    rewarm=True,
)
```

## Choosing a dispatcher

Each rule can pick its own dispatcher. The dispatcher decides where
the invalidation work runs.

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    dispatcher="celery",
    dispatcher_config={"queue": "cache-invalidation"},
)
```

`dispatcher` accepts either a registered name (`"celery"`,
`"django_rq"`, `"django_q"`, `"dramatiq"`, `"asyncio"`,
`"threadpool"`, `"inline"`) or a `Dispatcher` subclass.
`dispatcher_config` is merged on top of the dispatcher's settings
block.

See the [Dispatchers guide](dispatchers.md) for per-dispatcher
configuration.

## Batching

`batch=False` by default. When set to `True`, this rule may share a
dispatch with other rules that have the same dispatcher batch key.
Off by default because a single batch failure retries the whole
group, which is rarely the desired behaviour for cache invalidation.

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    dispatcher="celery",
    batch=True,
)
```

## Error handling

Errors that escape the registry are caught and logged by default, so
a transient failure in a worker does not crash the model save. To
make errors propagate (so a broker can retry or dead-letter), set
`raise_exception=True` on the rule, on the dispatcher's settings, or
globally.

```python
InvalidationRule(
    model=User,
    field_mapping={"user_id": "id"},
    raise_exception=True,
)
```

The resolution order, highest priority first:

1. `InvalidationRule.raise_exception`.
2. The per-dispatcher `RAISE_EXCEPTION` setting.
3. `RESTFLOW_SETTINGS["CACHE_SETTINGS"]["DISPATCHER_RAISE_EXCEPTION"]`
   (default `False`).

When a batch mixes explicit values, `True` wins so the error
surfaces.

## Where to next

- [Dispatchers](dispatchers.md): pick where invalidation runs and
  configure each broker.
- [cache_result](cache-result.md): the decorator that pairs with
  these rules.
- [Settings](../settings.md): tune the dispatcher defaults globally.

# PostFetch

`PostFetch` attaches related rows to a list of base objects after
the base query has run. It exists for the cases that
`prefetch_related` cannot reach: post-pagination joins, denormalised
counts, cross-database joins, or "latest match per item" lookups.

## When to use it

`prefetch_related` is the right tool for most "fetch related rows"
problems. It supports nested relations, custom querysets through
`Prefetch`, and slicing through the `_prefetched_objects_cache`. Use
PostFetch when prefetch_related cannot express the join.

Common reasons.

- The base sequence is paginated, and the join should run after
  pagination so the relation is fetched only for the visible page.
- The related rows live on a different database, so a SQL JOIN cannot
  be expressed.
- Only the latest related row per base item is needed, and slicing
  through Prefetch is too expensive.
- The base sequence is a list of dicts (for example, after
  `.values()`) and prefetch hooks no longer apply.

## Constructor

```python
PostFetch(
    queryset,
    to_attr,
    values,
    values_dict=None,
    limit=1,
    order_by=None,
    **queries,
)
```

| Argument     | Purpose                                                     |
| ------------ | ----------------------------------------------------------- |
| queryset     | The secondary queryset to read from                         |
| to_attr      | Attribute or dict key on each base item to attach onto      |
| values       | Field names to retrieve via `qs.values(*values)`            |
| values_dict  | Annotated value expressions to retrieve                     |
| limit        | 1 / int / None -- how many matches to attach                |
| order_by     | Fields applied to the secondary queryset before grouping    |
| **queries    | Mapping of secondary_field -> base_field                    |

## The queries kwarg

`**queries` is the join specification. Each entry maps a secondary
field name to a base field name. The matching pseudocode.

```python
keys_per_base = [base_item[base_field] for base_item in base_seq]
qs = secondary.filter(secondary_field__in=keys_per_base)
grouped = group_by(qs, secondary_field)
for base_item in base_seq:
    matches = grouped.get(base_item[base_field], [])
    base_item[to_attr] = pick(matches, limit, order_by)
```

Multi-field joins are supported by passing more than one keyword
argument; the lookup uses a tuple of values per base item.

```python
PostFetch(
    queryset=Stock.objects.all(),
    to_attr="stock",
    values=["product_id", "warehouse_id", "quantity"],
    product_id="id",
    warehouse_id="warehouse_id",
)
```

## limit

The `limit` argument controls how many matched rows are attached.

| Value           | Effect                                           |
| --------------- | ------------------------------------------------ |
| 1 (default)     | Attaches the first match. None when missing.     |
| Integer N > 1   | Attaches a list of up to N matches.              |
| None            | Attaches the full list of matches.               |

For "latest review per product" semantics, combine `limit=1` with
`order_by=["-created_at"]`. For "all reviews per product (page only)",
use `limit=None`.

## order_by

The `order_by` list is applied to the secondary queryset before
grouping. It changes which rows end up first in each group, so it
governs the result returned by `limit=1` or `limit=N`.

```python
PostFetch(
    queryset=Review.objects.all(),
    to_attr="latest_review",
    values=["id", "rating", "comment"],
    order_by=["-created_at"],
    limit=1,
    product_id="id",
)
```

## values and values_dict

`values` is the standard `qs.values(*values)` shape. The join key
fields are appended automatically when missing, so the grouping step
can read them out of each row. The list is copied per fetch call, so
sharing a PostFetch instance between requests is safe.

`values_dict` enables annotated expressions.

```python
from django.db.models.functions import Upper

PostFetch(
    queryset=Review.objects.all(),
    to_attr="latest_review",
    values=["id", "rating"],
    values_dict={"comment_upper": Upper("comment")},
    limit=1,
    product_id="id",
)
```

The two are merged into the underlying call as
`qs.values(*values, **values_dict)`.

## to_attr

The `to_attr` argument is the attribute (or dict key) on each base
item where the matched row attaches.

- For model instances, the attribute is set via `setattr(item, to_attr, value)`.
- For dicts, the dict key is set via `item[to_attr] = value`.

The PostFetch detects the item shape per call, so a list of dicts
returned by `qs.values(...)` and a list of model instances are both
supported.

## Sync and async paths

`PostFetch` exposes both `fetch` and `afetch`.

```python
items = post_fetch.fetch(queryset)
items = await post_fetch.afetch(queryset)
```

Both methods materialise the base sequence once. Repeated iteration
over the same base sequence does not re-run the underlying queryset.
The async path uses `async for` to walk the secondary queryset, so it
plays nicely with Django's async ORM hooks.

## Integration with views

The view helpers `serialized_response` and `paginated_response` (and
their async variants) accept a `post_fetches=` argument. The helpers run
each PostFetch before serialising, so the `to_attr` is available to
the serializer.

```python
class ProductListView(AsyncListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    pagination_class = PageNumberPagination

    async def get(self, request, *args, **kwargs):
        latest_review = PostFetch(
            queryset=Review.objects.all(),
            to_attr="latest_review",
            values=["id", "rating", "comment"],
            order_by=["-created_at"],
            limit=1,
            product_id="id",
        )
        return await self.apaginated_response(
            self.get_queryset(),
            post_fetches=[latest_review],
        )
```

The serializer can read `obj.latest_review` (or `obj["latest_review"]`
when the items are dicts) like any other attribute.

## Worked example

Attach the latest review to each product on a paginated list.

```python
from restflow.views import (
    AsyncListAPIView,
    PostFetch,
)

class ProductListView(AsyncListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    pagination_class = PageNumberPagination
    filter_backends = [RestflowFilterBackend]
    filterset_class = ProductFilterSet

    async def get(self, request, *args, **kwargs):
        latest_review = PostFetch(
            queryset=Review.objects.all(),
            to_attr="latest_review",
            values=["id", "rating", "comment", "created_at"],
            order_by=["-created_at"],
            limit=1,
            product_id="id",
        )
        return await self.apaginated_response(
            self.get_queryset(),
            post_fetches=[latest_review],
        )
```

The serializer reads `obj.latest_review` and renders it. When the
product has no reviews, `latest_review` is None.

For multiple PostFetch instances, pass a list. Each runs in order,
once per request.

```python
return await self.apaginated_response(
    self.get_queryset(),
    post_fetches=[latest_review, sales_count, low_stock_warehouse],
)
```

## Performance

A PostFetch runs one extra query per call, regardless of page size.
The query is `secondary.filter(secondary_field__in=[...]).values(...)`,
so the cost scales with the number of distinct join keys on the page.

The grouping step is in-process Python and runs in O(matches) time.
For typical page sizes (under a few hundred items) the overhead is
negligible compared to the underlying SQL round-trip.

To skip the secondary query entirely when the page has no items, the
fetch returns immediately. To skip when no item carries a join key, the
fetch attaches the empty value (None for limit=1, [] otherwise) without
hitting the database.

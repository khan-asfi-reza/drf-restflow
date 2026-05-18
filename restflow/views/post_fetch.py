from typing import Any


class PostFetch:
    """
    Attaches related data to a list of base objects after they have been
    fetched or paginated. Useful when prefetch_related cannot be used.

        post_fetch = PostFetch(
            queryset=Content.objects.all(),
            to_attr="content_data",
            limit=1,
            order_by=("-created_at",),
            values=["id", "title", "created_at"],
            content_id="content_ptr_id",
        )
        enriched = post_fetch.fetch(base_items)

    Use afetch in async views.
    """

    def __init__(
        self,
        queryset: Any,
        to_attr: str,
        values: list[str],
        values_dict: dict[str, Any] | None = None,
        limit: int | None = 1,
        order_by: list[str] | None = None,
        **queries: str,
    ):
        """Configure the post-fetch.

        Args:
            queryset: Secondary queryset to retrieve data from.
            to_attr: Attribute or dict key under which the matched objects
                are attached on each base item.
            values: Field names retrieved via `qs.values(*values)`. Copied
                per fetch call; safe to share between instances.
            values_dict: Annotated value expressions passed as
                `qs.values(**values_dict)`. For example
                `{"upper_name": Upper("name")}`.
            limit: 1 attaches the first match (or None when missing). An
                integer greater than 1 attaches a list of up to that many
                matches. None attaches all matches.
            order_by: Fields applied to the secondary queryset before
                grouping.
            **queries: Mapping of secondary_field -> base_field. Each
                base item's `base_field` is collected and the secondary
                queryset is filtered with `secondary_field__in=[...]`.
        """
        self.queryset = queryset
        self.to_attr = to_attr
        self.limit = limit
        self.order_by = order_by
        self.values = values
        self.queries = queries
        self.values_dict = values_dict or {}

    @staticmethod
    def get_value(obj, attr, default=None):
        """
        Returns the named attribute or dict key from a base item.
        """
        if isinstance(obj, dict):
            return obj.get(attr, default)
        return getattr(obj, attr, default)

    def build_key_tuple(self, obj, field_mapping):
        """
        Returns a tuple of join values for an item, or None if any join field
        is missing.
        """
        values_list = []
        for _secondary_field, base_field in field_mapping.items():
            val = self.get_value(obj, base_field)
            if val is None:
                return None
            values_list.append(val)
        return tuple(values_list)

    def build_filter_kwargs(self, base_queryset):
        """
        Returns the secondary_field__in lookup map used to fetch related rows.
        """
        filter_kwargs = {
            f"{secondary_field}__in": set()
            for secondary_field in self.queries
        }
        for item in base_queryset:
            key_tuple = self.build_key_tuple(item, self.queries)
            if key_tuple is None:
                continue
            for (secondary_field, _), val in zip(
                self.queries.items(), key_tuple, strict=True
            ):
                filter_kwargs[f"{secondary_field}__in"].add(val)
        return {k: list(v) for k, v in filter_kwargs.items()}

    def _empty_value(self):
        return [] if self.limit is None or self.limit != 1 else None

    def _attach_empty(self, base_queryset):
        empty = self._empty_value()
        for item in base_queryset:
            self._set(item, empty)

    def _set(self, item, value):
        if isinstance(item, dict):
            item[self.to_attr] = value
        else:
            setattr(item, self.to_attr, value)

    def _resolve_values(self):
        values = list(self.values)
        for q in self.queries:
            if q not in values:
                values.append(q)
        return values

    def _key_from_secondary(self, obj):
        key_values = []
        for secondary_field in self.queries:
            val = self.get_value(obj, secondary_field)
            if val is None:
                return None
            key_values.append(val)
        return tuple(key_values)

    def _select_for(self, key_tuple, grouped):
        if key_tuple is None:
            return self._empty_value()
        matches = grouped.get(key_tuple, [])
        if self.limit is None:
            return matches
        if self.limit == 1:
            return matches[0] if matches else None
        return matches[: self.limit]

    def fetch(self, base_queryset):
        """
        Attaches matching secondary rows to each base item and returns the
        list. The base sequence is materialized once so repeated iteration
        does not re-execute the queryset.
        """
        items = list(base_queryset)
        if not items:
            return items

        filter_kwargs = self.build_filter_kwargs(items)
        if all(len(v) == 0 for v in filter_kwargs.values()):
            self._attach_empty(items)
            return items

        qs = self.queryset.filter(**filter_kwargs)
        if self.order_by:
            qs = qs.order_by(*self.order_by)
        qs = qs.values(*self._resolve_values(), **self.values_dict)

        grouped = {}
        for obj in qs:
            key = self._key_from_secondary(obj)
            if key is None:
                continue
            grouped.setdefault(key, []).append(obj)

        for item in items:
            key_tuple = self.build_key_tuple(item, self.queries)
            self._set(item, self._select_for(key_tuple, grouped))

        return items

    async def afetch(self, base_queryset):
        """
        Async equivalent of fetch, iterating the secondary queryset with
        async for. The base sequence is materialized once.
        """
        items = list(base_queryset)
        if not items:
            return items

        filter_kwargs = self.build_filter_kwargs(items)
        if all(len(v) == 0 for v in filter_kwargs.values()):
            self._attach_empty(items)
            return items

        qs = self.queryset.filter(**filter_kwargs)
        if self.order_by:
            qs = qs.order_by(*self.order_by)
        qs = qs.values(*self._resolve_values(), **self.values_dict)

        grouped = {}
        async for obj in qs:
            key = self._key_from_secondary(obj)
            if key is None:
                continue
            grouped.setdefault(key, []).append(obj)

        for item in items:
            key_tuple = self.build_key_tuple(item, self.queries)
            self._set(item, self._select_for(key_tuple, grouped))

        return items

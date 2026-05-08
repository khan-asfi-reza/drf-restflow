import asyncio

from restflow.views import PostFetch


def _run(coro):
    return asyncio.run(coro)


class _StubAsyncIter:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for item in self._items:
            yield item


class _StubQuerySet:
    def __init__(self, items, filter_kwargs=None):
        self._items = list(items)
        self._filter_kwargs = filter_kwargs or {}

    def filter(self, **kwargs):
        out = []
        for item in self._items:
            if all(item.get(field.split("__")[0]) in vals for field, vals in kwargs.items()):
                out.append(item)
        return _StubQuerySet(out, kwargs)

    def order_by(self, *fields):
        items = list(self._items)
        for field in reversed(fields):
            reverse = field.startswith("-")
            key = field.lstrip("-")
            items.sort(key=lambda x: x[key], reverse=reverse)
        return _StubQuerySet(items, self._filter_kwargs)

    def values(self, *fields, **expressions):
        if not fields and not expressions:
            return self
        out = []
        for item in self._items:
            row = {f: item.get(f) for f in fields}
            for alias, expr in expressions.items():
                row[alias] = expr(item)
            out.append(row)
        return _StubQuerySet(out, self._filter_kwargs)

    def __iter__(self):
        return iter(self._items)

    def __aiter__(self):
        return _StubAsyncIter(self._items).__aiter__()


# Sync fetch tests


def test_fetch_single_key_limit_1_attaches_first_match():
    secondary = _StubQuerySet([
        {"content_id": 1, "title": "A"},
        {"content_id": 2, "title": "B"},
    ])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=["title"],
        limit=1,
        content_id="content_ptr_id",
    )
    base = [{"content_ptr_id": 1}, {"content_ptr_id": 2}]
    pf.fetch(base)
    assert base[0]["content"] == {"content_id": 1, "title": "A"}
    assert base[1]["content"] == {"content_id": 2, "title": "B"}


def test_fetch_limit_1_returns_none_for_unmatched():
    secondary = _StubQuerySet([{"content_id": 1, "title": "A"}])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=["title"],
        limit=1,
        content_id="content_ptr_id",
    )
    base = [{"content_ptr_id": 1}, {"content_ptr_id": 99}]
    pf.fetch(base)
    assert base[0]["content"] == {"content_id": 1, "title": "A"}
    assert base[1]["content"] is None


def test_fetch_limit_n_attaches_capped_list():
    secondary = _StubQuerySet([
        {"content_id": 1, "title": "A1"},
        {"content_id": 1, "title": "A2"},
        {"content_id": 1, "title": "A3"},
    ])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=["title"],
        limit=2,
        content_id="content_ptr_id",
    )
    base = [{"content_ptr_id": 1}]
    pf.fetch(base)
    assert len(base[0]["content"]) == 2


def test_fetch_limit_none_attaches_all_matches():
    secondary = _StubQuerySet([
        {"content_id": 1, "title": "A1"},
        {"content_id": 1, "title": "A2"},
        {"content_id": 1, "title": "A3"},
    ])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=["title"],
        limit=None,
        content_id="content_ptr_id",
    )
    base = [{"content_ptr_id": 1}]
    pf.fetch(base)
    assert len(base[0]["content"]) == 3


def test_fetch_multi_key_match():
    secondary = _StubQuerySet([
        {"content_id": 1, "tenant_id": 10, "title": "A"},
        {"content_id": 1, "tenant_id": 20, "title": "B"},
    ])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=["title"],
        limit=1,
        content_id="content_ptr_id",
        tenant_id="tenant_ptr_id",
    )
    base = [{"content_ptr_id": 1, "tenant_ptr_id": 20}]
    pf.fetch(base)
    assert base[0]["content"]["title"] == "B"


def test_fetch_handles_object_instances():
    class _Obj:
        def __init__(self, content_ptr_id):
            self.content_ptr_id = content_ptr_id

    secondary = _StubQuerySet([{"content_id": 1, "title": "A"}])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=["title"],
        limit=1,
        content_id="content_ptr_id",
    )
    obj = _Obj(content_ptr_id=1)
    pf.fetch([obj])
    assert obj.content == {"content_id": 1, "title": "A"}


def test_fetch_skips_base_items_with_none_key():
    secondary = _StubQuerySet([{"content_id": 1, "title": "A"}])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=["title"],
        limit=1,
        content_id="content_ptr_id",
    )
    base = [{"content_ptr_id": 1}, {"content_ptr_id": None}]
    pf.fetch(base)
    assert base[0]["content"] == {"content_id": 1, "title": "A"}
    assert base[1]["content"] is None


def test_fetch_empty_base_returns_empty():
    pf = PostFetch(
        queryset=_StubQuerySet([]),
        to_attr="content",
        values=["title"],
        content_id="content_ptr_id",
    )
    assert pf.fetch([]) == []


def test_fetch_no_matches_attaches_empty_value():
    secondary = _StubQuerySet([])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=["title"],
        limit=1,
        content_id="content_ptr_id",
    )
    base = [{"content_ptr_id": 1}]
    pf.fetch(base)
    assert base[0]["content"] is None


def test_fetch_does_not_mutate_user_supplied_values_list():
    user_values = ["title"]
    secondary = _StubQuerySet([{"content_id": 1, "title": "A"}])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=user_values,
        limit=1,
        content_id="content_ptr_id",
    )
    pf.fetch([{"content_ptr_id": 1}])
    pf.fetch([{"content_ptr_id": 1}])
    assert user_values == ["title"]


def test_fetch_with_order_by():
    secondary = _StubQuerySet([
        {"content_id": 1, "title": "A1", "created_at": 1},
        {"content_id": 1, "title": "A2", "created_at": 3},
        {"content_id": 1, "title": "A3", "created_at": 2},
    ])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=["title", "created_at"],
        limit=1,
        order_by=("-created_at",),
        content_id="content_ptr_id",
    )
    base = [{"content_ptr_id": 1}]
    pf.fetch(base)
    assert base[0]["content"]["title"] == "A2"


# Async afetch tests


def test_afetch_single_key_limit_1():
    secondary = _StubQuerySet([
        {"content_id": 1, "title": "A"},
        {"content_id": 2, "title": "B"},
    ])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=["title"],
        limit=1,
        content_id="content_ptr_id",
    )
    base = [{"content_ptr_id": 1}, {"content_ptr_id": 2}]
    _run(pf.afetch(base))
    assert base[0]["content"]["title"] == "A"
    assert base[1]["content"]["title"] == "B"


def test_afetch_limit_n_async():
    secondary = _StubQuerySet([
        {"content_id": 1, "title": "A1"},
        {"content_id": 1, "title": "A2"},
        {"content_id": 1, "title": "A3"},
    ])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=["title"],
        limit=2,
        content_id="content_ptr_id",
    )
    base = [{"content_ptr_id": 1}]
    _run(pf.afetch(base))
    assert len(base[0]["content"]) == 2


def test_afetch_no_matches_attaches_empty_value():
    secondary = _StubQuerySet([])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=["title"],
        limit=None,
        content_id="content_ptr_id",
    )
    base = [{"content_ptr_id": 1}]
    _run(pf.afetch(base))
    assert base[0]["content"] == []


def test_afetch_empty_base_returns_empty():
    pf = PostFetch(
        queryset=_StubQuerySet([]),
        to_attr="content",
        values=["title"],
        content_id="content_ptr_id",
    )
    assert _run(pf.afetch([])) == []


def test_fetch_attaches_empty_when_all_base_keys_are_none():
    secondary = _StubQuerySet([{"content_id": 1, "title": "A"}])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=["title"],
        limit=1,
        content_id="content_ptr_id",
    )
    base = [{"content_ptr_id": None}, {"content_ptr_id": None}]
    pf.fetch(base)
    assert base[0]["content"] is None
    assert base[1]["content"] is None


def test_fetch_attaches_empty_list_when_all_base_keys_are_none_with_limit_none():
    secondary = _StubQuerySet([{"content_id": 1, "title": "A"}])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=["title"],
        limit=None,
        content_id="content_ptr_id",
    )
    base = [{"content_ptr_id": None}]
    pf.fetch(base)
    assert base[0]["content"] == []


class _PassThroughQuerySet(_StubQuerySet):
    def filter(self, **kwargs):
        return _PassThroughQuerySet(self._items, kwargs)


def test_fetch_skips_secondary_rows_with_none_join_value():
    secondary = _PassThroughQuerySet([
        {"content_id": None, "title": "Skip"},
        {"content_id": 1, "title": "Keep"},
    ])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=["title"],
        limit=1,
        content_id="content_ptr_id",
    )
    base = [{"content_ptr_id": 1}]
    pf.fetch(base)
    assert base[0]["content"]["title"] == "Keep"


def test_afetch_attaches_empty_when_all_base_keys_are_none():
    secondary = _StubQuerySet([{"content_id": 1, "title": "A"}])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=["title"],
        limit=1,
        content_id="content_ptr_id",
    )
    base = [{"content_ptr_id": None}]
    _run(pf.afetch(base))
    assert base[0]["content"] is None


def test_afetch_skips_secondary_rows_with_none_join_value():
    secondary = _PassThroughQuerySet([
        {"content_id": None, "title": "Skip"},
        {"content_id": 1, "title": "Keep"},
    ])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=["title"],
        limit=1,
        content_id="content_ptr_id",
    )
    base = [{"content_ptr_id": 1}]
    _run(pf.afetch(base))
    assert base[0]["content"]["title"] == "Keep"


def test_afetch_with_order_by():
    secondary = _StubQuerySet([
        {"content_id": 1, "title": "A1", "created_at": 1},
        {"content_id": 1, "title": "A2", "created_at": 3},
        {"content_id": 1, "title": "A3", "created_at": 2},
    ])
    pf = PostFetch(
        queryset=secondary,
        to_attr="content",
        values=["title", "created_at"],
        limit=1,
        order_by=("-created_at",),
        content_id="content_ptr_id",
    )
    base = [{"content_ptr_id": 1}]
    _run(pf.afetch(base))
    assert base[0]["content"]["title"] == "A2"

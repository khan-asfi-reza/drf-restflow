# ValidatedData

`ValidatedData` is the dict subclass that `Serializer.validated_data`
hands back when a payload has cleared validation. It behaves as a
plain dict everywhere a dict is expected, and adds two pieces of
sugar that make request handlers easier to read: attribute access
and a JSON helper that already knows about `Decimal`, `datetime`,
`date`, `time`, and `UUID`.

## Reading and writing

`ValidatedData` is a dict subclass, so `vd["name"]`, `vd.get("name")`,
`**vd`, and `dict(vd)` all work the way they do on a regular dict.
The class adds attribute access on top.

```python
serializer = ProductSerializer(data=request.data)
serializer.is_valid(raise_exception=True)
data = serializer.validated_data

data.name           # same as data["name"]
data["name"]
data.get("name")
{**data}            # plain dict copy
```

Writes go through to the underlying dict.

```python
data.discount = Decimal("0.10")
data["discount"] == Decimal("0.10")  # True
```

`del data.field` and `del data["field"]` both raise `AttributeError`
or `KeyError` respectively when the key is missing, matching the
attribute and item lookup paths.

## Nested payloads

Nested dicts and lists of dicts are converted recursively when the
serializer assembles `validated_data`, so attribute access carries
through nested structures.

```python
order = serializer.validated_data
order.customer.email          # nested dict
order.items[0].sku            # list of nested dicts
```

Existing `ValidatedData` instances in the tree are left in place.

## JSON output

`to_json(**opts)` renders the payload as a JSON string. The keyword
arguments are forwarded straight to `json.dumps`. A custom `default`
callable is composed with the restflow fallback so a payload with
`Decimal`, `datetime`, `date`, `time`, and `UUID` values renders
without writing a custom encoder.

```python
order.to_json()                                 # default formatting
order.to_json(indent=2, sort_keys=True)         # extra json.dumps kwargs
order.to_json(default=my_encoder)               # my_encoder runs first; restflow handles the rest
```

The fallback maps:

- `Decimal` to its string form
- `datetime`, `date`, `time` to ISO 8601
- `UUID` to its string form
- `ValidatedData` to a plain dict copy

`__json__()` returns a plain dict. Codecs and libraries that look
up `__json__` see a regular dict shape rather than the subclass.

## Pickling

`__reduce__` is implemented, so `ValidatedData` instances pickle
and unpickle as plain dicts wrapped back into `ValidatedData` on
load. The same instance is safe to hand to `pickle`,
`copy.deepcopy`, or any cache backend that needs a serialized
form.

## When to reach for it

`Serializer.validated_data` is already a `ValidatedData` instance
in restflow, so no opt-in is needed. The shape matters most in
view code that wants attribute access for readability:

```python
async def post(self, request):
    serializer = OrderSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    payload = serializer.validated_data

    order = await Order.objects.acreate(
        customer=payload.customer,
        total=payload.total,
    )
    return await self.aserialized_response(order, status=201)
```

The same code with `payload["customer"]` is equivalent. Pick the
form that reads better in the surrounding view.

## API

::: restflow.serializers.validated_data.ValidatedData
    options:
      show_source: false
      heading_level: 3

::: restflow.serializers.validated_data.transform_validated_data
    options:
      show_source: false
      heading_level: 3

# Field Types

Concrete field classes used inside a `FilterSet`. See the
[Fields guide](../../guide/filtering/fields.md) for an overview and
worked examples.

::: restflow.filters.StringField

::: restflow.filters.IntegerField

::: restflow.filters.FloatField

::: restflow.filters.BooleanField

::: restflow.filters.DecimalField

::: restflow.filters.DateField

::: restflow.filters.DateTimeField

::: restflow.filters.TimeField

::: restflow.filters.DurationField

::: restflow.filters.ChoiceField

::: restflow.filters.MultipleChoiceField

::: restflow.filters.ListField

::: restflow.filters.OrderField

::: restflow.filters.RelatedField

::: restflow.filters.EmailField

::: restflow.filters.IPAddressField

## Type aliases

`Email` and `IPAddress` are `NewType` aliases that map to
`EmailField` and `IPAddressField` when used as type annotations on a
FilterSet.

```python
from restflow.filters import Email, IPAddress


class ContactFilterSet(FilterSet):
    contact_email: Email
    server_ip: IPAddress
```

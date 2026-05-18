# Permission combinators

DRF supports boolean composition of permission classes through the
`&`, `|`, and `~` operators with brackets for grouping. Operators
follow Python's logical precedence (`~` highest, then `&`, then `|`).
Restflow ships async-native subclasses of DRF's combinator
classes so combinator branches resolve through the async hook
.

See the [Permissions guide](../../guide/permissions/index.md#combinators)
for short-circuit behaviour and worked examples.

::: restflow.permissions.AND

::: restflow.permissions.OR

::: restflow.permissions.NOT

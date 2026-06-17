import datetime
import decimal
import inspect
from collections.abc import Callable
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    Optional,
)

if TYPE_CHECKING:
    from restflow.filters.filters import FilterSet

from django.db.models import Model, Q, QuerySet
from django.db.models.fields import Field as DjangoField
from rest_framework import fields as drf_fields
from rest_framework.request import Request
from rest_framework.utils import model_meta

from restflow.helpers import Email, IPAddress, resolve_field_from_type

LOOKUP_CATEGORIES = {
    "basic": ["exact", "in", "isnull"],
    "text": ["icontains", "contains", "startswith", "endswith", "iexact"],
    "comparison": ["gt", "gte", "lt", "lte", ],
    "date": ["date", "year", "month", "day", "week", "week_day", "quarter"],
    "time": ["time", "hour", "minute", "second"],
    "postgres": ["search", "trigram_similar", "unaccent"],
    "pg_array": ["contains", "overlaps", "contained_by"],
    # Regex lookups are potentially expensive/dangerous, opt in explicitly.
    "unsafe": ["regex", "iregex"],
}

# Default lookup configuration by Django field type
DEFAULT_FIELD_LOOKUPS = {
    # Text fields
    "CharField": ["basic", "text"],
    "TextField": ["basic", "text"],
    "EmailField": ["basic", "text"],
    "URLField": ["basic", "text"],
    "SlugField": ["basic", "text"],
    # Numeric fields
    "IntegerField": ["basic", "comparison"],
    "BigIntegerField": ["basic", "comparison"],
    "SmallIntegerField": ["basic", "comparison"],
    "PositiveIntegerField": ["basic", "comparison"],
    "PositiveSmallIntegerField": ["basic", "comparison"],
    "FloatField": ["basic", "comparison"],
    "DecimalField": ["basic", "comparison"],
    # Date/Time fields
    "DateField": ["basic", "comparison", "date"],
    "DateTimeField": ["basic", "comparison", "date", "time"],
    "TimeField": ["basic", "comparison", "time"],
    "DurationField": ["basic", "comparison"],
    # Other fields
    "BooleanField": ["basic"],
    "IPAddressField": ["basic"],
    "GenericIPAddressField": ["basic"],
    "JSONField": ["basic"],
    # Relationship fields
    "ForeignKey": ["basic"],
    "OneToOneField": ["basic"],
    "ManyToManyField": ["basic"],
    # Default fallback
    "_default": ["basic"],
}


LOOKUP_SET = set(DjangoField.get_lookups().keys())

ALL_FIELDS = "__all__"

LookupsType = str | list[str] | tuple[str] | dict[str, dict[str, Any]] | None
FieldsType =  list[str] | tuple[str] | str


def extract_model_fields(model: type[Model], fields: FieldsType, exclude: list[str] | tuple[str], ) -> list[DjangoField]:
    """
    Returns a list of model fields based on the provided options.
    Args:
        model: Model class to extract fields from.
        fields: List of field names to include. If set to "__all__", all fields are included.
        exclude: List of field names to exclude.

    """
    if fields and fields != ALL_FIELDS and not isinstance(fields, (list, tuple)):
        msg = (
            f'The `fields` option must be a list or tuple or "__all__" '
            f"Got {type(fields).__name__}"
        )
        raise TypeError(msg)

    if exclude and not isinstance(exclude, (list, tuple)):
        msg = f"The `exclude` option must be a list or tuple. Got {type(exclude).__name__}"
        raise TypeError(msg)

    if model_meta.is_abstract_model(model):
        msg = f"Abstract models cannot be used. {model.__name__} is abstract."
        raise ValueError(msg)

    if fields == ALL_FIELDS:
        fields = model._meta.get_fields()
    else:
        fields = [model._meta.get_field(field) for field in fields]

    model_fields = []
    for field in fields:
        if field.name not in exclude:
            model_fields.append(field)
    return model_fields


def process_lookups(lookups: LookupsType, lookup_categories: list[str]) -> list[str] | dict[str, dict[str, Any]] | dict[str, str]:
    #
    # Expand lookup definitions into concrete ORM lookup names.
    #
    # - Category names inside list/options-dict form expand via LOOKUP_CATEGORIES.
    # - If `lookups == '__all__'`, expand all categories from `lookup_categories`.
    # - Empty / None input -> returns [].
    # `lookup_categories` is more like a default value.
    # Examples:
    # process_lookups([], ["comparison"]) -> ["gt", "gte", "lt", "lte"]
    #
    # process_lookups(["gt", "lt"], []) -> ["gt", "lt"]
    #
    # process_lookups(["comparison"], []) -> ["gt", "gte", "lt", "lte"]
    #
    # process_lookups({"comparison": {"x": 1}}, []) -> {"gt": {"x": 1}, "gte": {"x": 1}, "lt": {"x": 1}, "lte": {"x": 1}}
    #
    # Alias form (values are strings - no category expansion):
    # process_lookups({"max": "lte", "min": "gte"}, []) -> {"max": "lte", "min": "gte"}
    #
    if not lookups:
        return [] if not isinstance(lookups, dict) else {}

    if lookups == ALL_FIELDS:
        lookups = [cat for cat in lookup_categories if cat in LOOKUP_CATEGORIES]

    if not all(
        isinstance(lookup, str) for lookup in (lookups if isinstance(lookups, (list, tuple)) else lookups.keys())
    ):
        msg = "`lookups` must be a list of strings or dict with string keys"
        raise AssertionError(msg)

    if isinstance(lookups, dict) and lookups and all(isinstance(v, str) for v in lookups.values()):
        return dict(lookups)

    expanded = {} if isinstance(lookups, dict) else []

    items = lookups.items() if isinstance(lookups, dict) else [(lookup, None) for lookup in lookups]

    for lookup, value in items:
        concrete_lookups = LOOKUP_CATEGORIES.get(lookup, [lookup])
        if isinstance(lookups, dict):
            expanded.update(dict.fromkeys(concrete_lookups, value))
        else:
            expanded.extend(concrete_lookups)

    return expanded if isinstance(lookups, dict) else list(dict.fromkeys(expanded))


class Field(drf_fields.Field):
    """
    Base filter field that extends rest_framework's Field with filtering capabilities.

    Field inherits all validation logic from Django Rest Framework's Field class and
    adds support for filtering Django querysets. Each field can generate additional
    lookup and negation variants automatically.

    Automatic Field Generation:
        - Negation field: Every field creates a negation variant (e.g., "price!" for not equal)
          unless allow_negate=False
        - Lookup fields: Fields generate additional variants based on the lookups parameter
          (e.g., "price__gte", "price__lte" from lookups=["gte", "lte"])

    Parameters:
        filter_by: Defines how to filter the queryset.
            Can be:
            - String: Django ORM lookup expression (e.g., "name__icontains", "price__gte")
            - Callable: Function that receives (value) and returns either a dict
              for Q() or a Q object directly. Cannot be used with method parameter.


        lookups: Additional lookup expressions to generate
            as separate fields. Can be:
            - List of lookups: ["gte", "lte", "in"] creates price__gte, price__lte, price__in
            - Category name: "basic" expands to ["exact", "in", "isnull"]
            - ALL_FIELDS: Uses all lookups from the field's lookup_categories
            - Alias dict mapping variant suffix -> ORM lookup,
                example: {"max": "lte", "min": "gte"}.
                Used together with `lookup_separator` to control how variants are
                named on the query string. Keys are NOT expanded via lookup categories.

        lookup_separator: Separator placed between the field name and a lookup
            variant suffix when building variant names. When `None` (the default),
            the FilterSet's `Meta.lookup_separator` is used, if Meta does not set
            one either, falls back to `"__"` to match Django's lookup syntax
            (e.g. `price__gte`).


        method: Custom filtering method. Can be:
            - Callable: Function with signature (filterset, queryset, value) -> QuerySet or Q
            - String: Name of a method on the FilterSet class. The resolved
              method is called with (queryset, value), the filterset instance
              is reachable via `self` for instance methods.
            Either form may be `async def` when the FilterSet is driven via
            `afilter_queryset`, calling sync `filter_queryset` with an async
            method raises `TypeError`.
            Cannot be used with filter_by parameter.

        allow_negate: If False, prevents automatic creation of the negation field.
            Default is True.

        negate: If True, inverts the filter to exclude matching results.
            Default is False.

        required: If True, validation fails when the field is not provided.
            Default is False.

    Examples:
        Basic field with simple lookup::

            name = StringField(filter_by="name__icontains")

        Field with multiple lookups::

            price = IntegerField(lookups=["gte", "lte", "exact"])
            # Creates: price, price__gte, price__lte, price__exact, price!

        Field with custom method as a callable::

            def filter_by_date_range(filterset, queryset, value):
                # Some extra business logic
                return queryset.filter(created_at__range=value)

            date_range = Field(method=filter_by_date_range)

        Field with custom method as a string referring to a FilterSet method::

            class ProductFilterSet(FilterSet):
                date_range = Field(method="filter_by_date_range")

                def filter_by_date_range(self, queryset, value):
                    return queryset.filter(created_at__range=value)

        Field with callable filter_by::

            def custom_lookup(value):
                return Q(name__icontains=value) | Q(description__icontains=value)

            search = StringField(filter_by=custom_lookup)

    See Also:
        - IntegerField, StringField, DateTimeField: Specialized field types
        - ListField: For filtering with multiple values
        - OrderField: Special field for queryset ordering
    """

    lookup_categories = ["basic", "text"]

    def __init__(
            self,
            *,
            db_field="",
            filter_by: str | Callable[[Any], Any] | dict | None = None,
            lookups: LookupsType = None,
            lookup_separator: str | None = None,
            method: Callable[[Any, QuerySet, Any], tuple[Q,QuerySet] | Q | QuerySet] | str | None = None,
            negate: bool = False,
            required: bool = False,
            allow_negate: bool = True,
            **kwargs,
    ):
        if method and filter_by:
            msg = "`method` and `filter_by` cannot be used together."
            raise AssertionError(msg)

        if method and (not callable(method) and not isinstance(method, str)):
            msg = "`method` must be a callable or a string."
            raise TypeError(msg)

        if (method or filter_by) and lookups:
            msg = (
                "`lookups` cannot be combined with `method` or `filter_by`"
            )
            raise AssertionError(msg)

        self.db_field = db_field
        self.filter_by = filter_by
        self.lookups = process_lookups(lookups, self.lookup_categories)
        self.lookup_separator = lookup_separator
        self.method = method
        self.negate = negate
        self.allow_negate = allow_negate
        kwargs["required"] = required
        # Fields cannot be null for filter field
        kwargs.setdefault("allow_null", False)
        kwargs.setdefault("read_only", False)
        kwargs.setdefault("write_only", False)
        # Stash the residual kwargs so `clone()` can replay them on the cloned field.
        self._clone_extra_kwargs = dict(kwargs)
        super().__init__(**kwargs)

    def clone(self, _type=None, field_name=None, **inner_kwargs):
        """Return a copy of this field, optionally re-typed via annotation."""
        default_kwargs = dict(
            filter_by=self.filter_by,
            db_field=self.db_field,
            lookups=self.lookups,
            lookup_separator=self.lookup_separator,
            method=self.method,
            negate=self.negate,
            allow_negate=self.allow_negate,
            **self._clone_extra_kwargs,
        )
        default_kwargs.update(inner_kwargs)
        if _type is not None:
            return build_filter_field(
                _type, field_name=field_name, **default_kwargs
            )
        return self.__class__(**default_kwargs)

    def ensure_db_field(self, db_field: str):
        """Set db_field to the supplied default when neither filter_by, method, nor db_field is set."""
        if not (self.filter_by or self.method or self.db_field):
            self.db_field = db_field

    def get_method(self, filterset=None):
        """Return the resolved filter method, looking up string method names on the filterset."""
        method = self.method
        if isinstance(method, str):
            method = getattr(filterset, method)
        return method

    @property
    def _filter_expression(self):
        return self.filter_by or self.db_field or self.field_name

    def _finalize_method(self, result, queryset):
        # Note: negation is intentionally not applied here. The original sync
        # implementation only inverted Q objects produced by the filter_by
        # branch, the method branch passes the user's Q through untouched.
        # Preserving that to avoid an unrelated behavior change.
        q = None
        if isinstance(result, Q):
            q = result
        elif isinstance(result, QuerySet):
            queryset = result
        return queryset, q

    async def _await_method(self, awaitable, queryset):
        return self._finalize_method(await awaitable, queryset)

    def _apply_filter_by(self, queryset, value):
        q = None
        filter_by = self._filter_expression

        # Lookup expression can either be a string or a function
        if isinstance(filter_by, str):
            q = Q(**{filter_by: value})

        elif filter_by is not None and callable(filter_by):
            filter_by = filter_by(value)
            if isinstance(filter_by, dict):
                q = Q(**filter_by)

            elif isinstance(filter_by, Q):
                q = filter_by

            else:
                msg = (
                    f"Invalid lookup expression returned from filter_by "
                    f"function: `{filter_by}`, must be a `dict` or `django.models.Q` object"
                )
                raise AssertionError(
                    msg
                )
        if self.negate and q:
            q = ~q

        return queryset, q

    def apply_filter(
            self,
            filterset: "FilterSet",
            queryset: QuerySet,
            value: Any,
    ) -> tuple[QuerySet, Optional[Q]]:
        """
        Apply the field's filter to a queryset based on the validated value.

        The original idea is to always send a Q object to support operators, but if a user defines a method
        for this field, it can either return a Q object or a modified queryset.

        If `method` is an `async def` callable, this returns a coroutine that
        yields the `(queryset, q)` tuple instead. Sync callers should detect
        the coroutine and raise, async callers should await.

        Args:
            filterset: The FilterSet instance that contains this field.
            queryset: The Django queryset to filter.
            value: The validated value from query parameters (already cleaned by DRF validation).

        Returns:
            Tuple of (queryset, q_object). queryset is the modified
                queryset or the original when Q objects are used.
                q_object is the Q to combine with other filters, or
                None when the queryset was modified directly. Returns
                a coroutine yielding that tuple when method= is async.

        """
        if self.method:
            method = self.get_method(filterset)
            # String `method` resolves to an attribute on the filterset, an
            # instance method is already bound so `self` is implicitly the
            # filterset. Avoid passing it again as an explicit argument.
            if isinstance(self.method, str):
                result = method(queryset, value)
            else:
                result = method(filterset, queryset, value)
            if inspect.isawaitable(result):
                return self._await_method(result, queryset)
            return self._finalize_method(result, queryset)

        return self._apply_filter_by(queryset, value)

    def __str__(self):
        return (
            f"{self.__class__.__name__}(field_name='{self.field_name}',"
            f"db_field={self.db_field,}"
            f"filter_by='{self.filter_by}', "
            f"lookups='{self.lookups}', "
            f"method='{self.method}')"
        )

    def __repr__(self):
        return self.__str__()


class IntegerField(
    Field,
    drf_fields.IntegerField,
):
    lookup_categories = [
        "basic",
        "comparison",
    ]


class BooleanField(
    Field,
    drf_fields.BooleanField,
):
    lookup_categories = ["basic"]

    def get_value(self, dictionary):
        """Return empty for an absent parameter so a missing filter is skipped rather than coerced to False."""
        if self.field_name not in dictionary:
            return drf_fields.empty
        return super().get_value(dictionary)


class FloatField(
    Field,
    drf_fields.FloatField,
):
    lookup_categories = ["basic", "comparison"]


class StringField(
    Field,
    drf_fields.CharField,
):
    lookup_categories = ["basic", "text"]


class IPAddressField(
    Field,
    drf_fields.IPAddressField,
):
    lookup_categories = ["basic", "text"]


class EmailField(
    Field,
    drf_fields.EmailField,
):
    lookup_categories = ["basic", "text"]


class DecimalField(
    Field,
    drf_fields.DecimalField,
):
    lookup_categories = ["basic", "comparison"]

    # Default value for max_digits and decimal_places
    def __init__(self, *, max_digits=10, decimal_places=2, **kwargs):
        super().__init__(max_digits=max_digits, decimal_places=decimal_places, **kwargs)


class DateField(
    Field,
    drf_fields.DateField,
):
    lookup_categories = ["basic", "comparison", "date"]


class DateTimeField(
    Field,
    drf_fields.DateTimeField,
):
    lookup_categories = ["basic", "comparison", "date", "time"]


class TimeField(
    Field,
    drf_fields.TimeField,
):
    lookup_categories = ["basic", "comparison", "time"]


class DurationField(
    Field,
    drf_fields.DurationField,
):
    lookup_categories = ["basic", "comparison", "time"]



class ChoiceField(
    Field,
    drf_fields.ChoiceField,
):
    lookup_categories = [
        "basic",
    ]


class MultipleChoiceField(
    Field,
    drf_fields.MultipleChoiceField,
):
    lookup_categories = [
        "basic",
    ]

    def get_value(self, dictionary):
        """Return empty for an absent parameter so a missing filter is skipped rather than coerced to an empty list."""
        if self.field_name not in dictionary:
            return drf_fields.empty
        return super().get_value(dictionary)

    def to_internal_value(self, data):
        """Convert input data to internal Python representation. Splits comma-separated values whether they arrive as a single string or as elements of a list."""
        if isinstance(data, str):
            data = {s.strip() for s in data.split(",") if s.strip()}
        elif isinstance(data, (list, tuple, set)):
            flat = set()
            for item in data:
                if isinstance(item, str):
                    for piece in item.split(","):
                        stripped = piece.strip()
                        if stripped:
                            flat.add(stripped)
                else:
                    flat.add(item)
            data = flat
        return super().to_internal_value(data)


class OrderField(MultipleChoiceField):
    """
    OrderField allows users to specify one or more ordering criteria via query parameters.
    It supports both ascending and descending order, with optional direction override.
    The query parameter name defaults to "order_by" but can be configured via Meta.order_param.

    Parameters:
        fields: Available ordering options as (option_key, model_field)
            tuples.Example: [("price", "price"), ("name", "name")]

        labels: Human-readable labels for display as
            (option_key, label) tuples. If not provided, uses fields parameter.

        override_order_direction: Override Django's default ordering
            direction. The default is "asc". When set to "desc", the meaning of the "-" prefix
            is reversed.

    Examples:
        Manual OrderField declaration::

            class ProductFilterSet(FilterSet):
                order_by = OrderField(
                    fields=[("price", "price"), ("name", "name"), ("date", "created_at")],
                    labels=[("price", "Price"), ("name", "Product Name"), ("date", "Date Created")],
                )

        Automatic generation via Meta:

            class ProductFilterSet(FilterSet):
                class Meta:
                    model = Product
                    fields = ALL_FIELDS
                    order_fields = [("price", "price"), ("name", "name")]
                    order_field_labels = [("price", "Price"), ("name", "Name")]
                    override_order_direction = "asc"

        Usage in a request::

            # GET /products?order_by=price -> orders by price ascending
            # GET /products?order_by=-price -> orders by price descending
            # GET /products?order_by=name,-price -> orders by name asc, then price desc

    Note: OrderField automatically generates ascending and descending variants for each option

    """

    def __init__(
            self,
            *,
            fields: list[tuple[str, str]] | tuple[tuple[str, str], ...],
            labels: list[tuple[str, str]] | tuple[tuple[str, str], ...] | None = None,
            override_order_direction: Literal["asc", "desc"] = "asc",
            **kwargs,
    ):
        kwargs.pop("distinct", None)
        kwargs.pop("distinct_order", None)
        kwargs.pop("exclude", None)
        kwargs.pop("filter_by", "")
        kwargs.pop("lookups", None)
        kwargs.setdefault("allow_negate", True)
        self.fields = self.process_fields(fields)
        self.labels = self.process_labels(labels or fields)
        self.override_order_direction = override_order_direction
        self.choices = self.process_choices(self.labels)
        kwargs["choices"] = self.choices
        super().__init__(**kwargs)

    @staticmethod
    def process_fields(fields):
        ret = []
        for key, val in fields:
            ret.append((key, val))
            # The descending variant flips the existing `-` prefix on the
            # model-field side rather than blindly prepending another, so
            # `("published", "-published_at")` produces the intuitive pair
            # `("published", "-published_at"), ("-published", "published_at")`.
            inverted = val[1:] if val.startswith("-") else f"-{val}"
            ret.append((f"-{key}", inverted))
        return ret

    @staticmethod
    def process_labels(labels):
        if not labels:
            return []
        ret = []
        for key, val in labels:
            ret.append((key, val))
            ret.append((f"-{key}", f"{val}"))
        return ret

    def process_choices(self, choices):
        # The "-" prefix means "descending" by default. With
        # `override_order_direction="desc"`,
        # the prefix is inverted: a bare key
        # means descending and "-key" means ascending.
        override = self.override_order_direction == "desc"
        ret = []
        for key, val in choices:
            has_prefix = key.startswith("-")
            ascending = has_prefix if override else not has_prefix
            suffix = " (Ascending)" if ascending else " (Descending)"
            ret.append((key, f"{val}{suffix}"))
        return ret

    def apply_filter(
            self, filterset, queryset: QuerySet, value: list[str]
    ) -> tuple[QuerySet, Q | None]:
        if self.method:
            method = self.get_method(filterset)
            if isinstance(self.method, str):
                result = method(queryset, value)
            else:
                result = method(filterset, queryset, value)
            if inspect.isawaitable(result):
                return self._await_order(result)
            queryset = result
        else:
            field_map = dict(self.fields)
            override = self.override_order_direction == "desc"
            order_fields = []
            for val in value:
                order_field = field_map.get(val, val)
                if order_field.startswith("-") and override:
                    order_field = order_field[1:]
                elif override:
                    order_field = f"-{order_field}"
                order_fields.append(order_field)
            if order_fields:
                queryset = queryset.order_by(*order_fields)
        return queryset, None

    @staticmethod
    async def _await_order(awaitable):
        return await awaitable, None




class ListField(
    Field,
    drf_fields.ListField,
):
    """
    Field for filtering with multiple values (e.g., filtering by multiple IDs).
    ListField extends rest framework ListField with filtering capabilities, typically used with
    the "__in" lookup to filter by multiple values.

    Parameters:
        child: A DRF field instance that validates individual list items.
            For example, IntegerField() for a list of integers.

        filter_by: Django ORM lookup expression. Defaults to "field_name__in"
            when created from type annotations like List[int].

        lookups: Additional lookup variants to generate.

        method: Custom filtering method.


    Examples:
        Explicit ListField declaration::

            from restflow.fields import ListField, IntegerField

            class ProductFilterSet(FilterSet):
                ids = ListField(child=IntegerField(), filter_by="id__in")
                tags = ListField(child=StringField(), filter_by="tags__name__in")

        Using type annotations::

            class ProductFilterSet(FilterSet):
                ids: List[int] # Automatically creates ListField with IntegerField child
                tags: List[str] # Automatically creates ListField with StringField child

        Usage in requests::

            # Array format
            GET /products?ids=1&ids=2&ids=3

            # Comma-separated format (parsed automatically)
            GET /products?ids=1,2,3

    """

    lookup_categories = [
        "basic",
    ]

    def __init__(
            self,
            *,
            child: drf_fields.Field,
            filter_by: str | None = None,
            lookups: list[str] | None = None,
            method: Callable[[Request, QuerySet, Any], QuerySet] | None = None,
            **kwargs,
    ):
        kwargs.pop("child", None)
        child.source = None
        super().__init__(
            child=child,
            filter_by=filter_by,
            lookups=lookups,
            method=method,
            **kwargs,
        )


    def to_internal_value(self, data):
        """Convert input data to internal Python representation. Splits comma-separated values whether they arrive as a single string or as elements of a list."""
        if isinstance(data, str):
            data = [s.strip() for s in data.split(",") if s.strip()]
        elif isinstance(data, (list, tuple, set)):
            flat = []
            for item in data:
                if isinstance(item, str):
                    for piece in item.split(","):
                        stripped = piece.strip()
                        if stripped:
                            flat.append(stripped)
                else:
                    flat.append(item)
            data = flat
        return super().to_internal_value(data)



class RelatedField(Field):
    """Filter field that expands into the filter fields of a related Django model."""

    def __init__(self, *,
                 model: type[Model],
                 fields: str | list[str],
                 exclude: list[str] | tuple[str] | None=None,
                 extra_kwargs: dict[str, dict[str, Any]] | None=None,
                 **kwargs):
        self.model = model
        self.fields = fields
        self.extra_kwargs = extra_kwargs or {}
        self.exclude = exclude or []
        super().__init__(filter_by=None, **kwargs)

    def clone(self, _type=None, field_name=None, **__):
        return None  # pragma: no cover

    def get_model_fields(self):
        return extract_model_fields(model=self.model, fields=self.fields, exclude=self.exclude)

    def apply_filter(
            self,
            _,
            queryset: QuerySet,
            __,
    ) -> tuple[QuerySet, Optional[Q]]:
        return queryset, None  # pragma: no cover

    def get_method(self, *_):
        return None # pragma: no cover

    def __str__(self):
        return (f"{self.__class__.__name__}("
                f"model={self.model}, fields={self.fields}, extra_kwargs={self.extra_kwargs}, exclude_fields={self.exclude}"
                f")")

DataTypeSerializerMap: dict[type, type[Field]] = {
    int: IntegerField,
    float: FloatField,
    str: StringField,
    bool: BooleanField,
    datetime.datetime: DateTimeField,
    datetime.date: DateField,
    datetime.time: TimeField,
    datetime.timedelta: DurationField,
    decimal.Decimal: DecimalField,
    Email: EmailField,
    IPAddress: IPAddressField,
}

DRF_DATA_TYPE_CHILD_ASSERTION_ERROR = "`annotations` must be in {types}".format(
    types=(*tuple([t.__name__ for t in DataTypeSerializerMap]), Literal.__name__, list.__name__, list.__name__,
           "Optional[T]", "Union[T, None]")
)


def _filter_list_hook(field_kwargs, field_name, _inner):
    field_kwargs["filter_by"] = f"{field_name}__in"


def build_filter_field(data_type, field_name: str | None = None, **field_kwargs):
    """
    Resolve a Python type annotation to the matching filter Field instance.

    Filter-side adapter over `restflow.helpers.resolve_field_from_type`,
    plugging in the filter type map, list/choice field classes, and the
    `__in` list_field hook.
    """
    return resolve_field_from_type(
        data_type,
        type_map=DataTypeSerializerMap,
        field_name=field_name,
        list_field_class=ListField,
        list_field_hook=_filter_list_hook,
        choice_field_class=ChoiceField,
        error_message=DRF_DATA_TYPE_CHILD_ASSERTION_ERROR,
        **field_kwargs,
    )


LOOKUP_DEFAULT_FIELD = {
    "in": ListField,
    "isnull": BooleanField,
    "range": ListField,
}
